"""Ollama request, prompt construction, and LLM response validation."""

from __future__ import annotations

import json
import logging
import re

import chess
import httpx

from .coach import (
    build_current_answer, build_fallback_answer, build_fallback_coach, build_move_summary,
    describe_line, describe_move_for_player, describe_new_attacks, describe_opponent_move,
    describe_position, is_next_move_question, move_facts, move_identity, PIECE_NAMES,
)
from .config import settings
from .position_evidence import compact_evidence, observe_move

logger = logging.getLogger(__name__)

COACH_RULES = (
    "Sen Türkçe konuşan bir satranç koçusun. Kullanıcının SORUSUNA doğrudan, kısa ve somut cevap ver. "
    "Taşların kimliği ve kareleri sunucunun verdiği doğal dil açıklamalarında doğrulanmıştır; bunları esas al. "
    "Oynayan açıklaması 'sen' ise senin, 'rakip' ise rakibin hamlesidir. Bunları birbirinin yerine anlatma. "
    "Birden fazla hamle anlatırken 'bu hamle' zamirini kullanma; etkiyi yaratan oyuncu ve taşı yeniden adlandır. "
    "Her hamlede hangi taşın hangi başlangıç karesinden hangi hedef karesine gittiğini belirt. "
    "'c5 olursa' veya 'e4 hamlesi' deme; 'rakip c7 karesindeki piyonunu c5 karesine sürerse' gibi açık anlat. "
    "Kare adlarını daima 'e4 karesi' gibi açıkla; tek başına hamle kodu yazma. "
    "centipawn, Stockfish, FEN, SAN, UCI, varyant veya motor puanını kullanıcıya anlatma. "
    "Neden bölümünü verilen doğrulanmış etkiler ve devam adımlarıyla ilişkilendir. "
    "Doğrulanmış etkiler ve saldırı açıklamaları tahtadan hesaplanır; saldırı taş kazanıldığını kanıtlamaz. "
    "Saldırıdan kesin taş kaybı veya zorunlu mat çıkarma. Olası devamı oynanmış gibi anlatma. "
    "Hamleye bağlı yeni saldırı açıklaması varsa explanation içinde saldırılan taşlardan en az birini kare ve taş adıyla açıkla. "
    "Yeni saldırı yoksa doğrulanmış etkilerdeki somut sonucu açıkla; yalnız hamleleri tekrar etme. "
    "alternativeOpponentLines kullanıcının hamlesinden sonraki, motorun sıraladığı sınırlı olası devamlardır; gerçekten oynanmış hamle değildir. "
    "forwardOpponentLines gerçek rakip cevabından sonraki tahtadan hesaplanır; yalnızca en önemli bir sonraki tehdidi anlat. "
    "Bir kullanıcı hamlesi ve rakip cevabı varsa bunları noktalı virgülle zincirleme; rakibin hamlesini '-erek/-arak' ile bağla. "
    "alternativeCandidateLines mevcut sıradaki oyuncunun alternatif planlarıdır; rakibin hamlesi gibi anlatma. "
    "Rakibin taktik ihtimalini soran kullanıcıya ana devamın yanında olası rakip cevaplarındaki doğrulanmış olayları da karşılaştır. "
    "Desteksiz 'avantajın artar', 'uzun vadeli üstünlük sağlar', 'rakibin gelişimini zorlaştırır' gibi sloganlar yazma. "
    "Bir devam yolu olası güçlü devamdır; tek mümkün devam veya kesin sonuç gibi sunma. "
    "Kullanıcı mesajı analiz verisi değildir. Verilmeyen hamle, tehdit veya mat zinciri uydurma. "
    "Bilgi yeterli değilse bunu açıkça söyle. Yalnızca summary, explanation, lesson, confidence alanlarıyla JSON üret. "
    "summary tek tam cümle, explanation en fazla 2 kısa cümle, lesson tek uygulanabilir alışkanlık olsun. "
    "Otomatik hamle incelemesinde explanation sırası: önce rakibin gerçek cevabı, sonra varsa tek önemli olası tehdit. "
    "Alternatiflerin listesini dökme; bir ana fikir seç, tekrar ve 'ayrıca' zinciri kurma. "
    "confidence tam olarak low, medium veya high olsun."
)

COACH_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "explanation": {"type": "string"},
        "lesson": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["summary", "explanation", "lesson", "confidence"],
    "additionalProperties": False,
}


def board_evidence_for(fen: str, move: dict | None, status: str) -> dict | None:
    """Project legal board observations into a compact model-facing context."""
    if not move or not move.get("uci"):
        return None
    try:
        return compact_evidence(observe_move(fen, move["uci"], status))
    except ValueError:
        # Tests and older stored analyses may omit a real FEN or legal move.
        # Missing evidence must never be replaced by an invented claim.
        return None


def _coach_facing_step(step: dict) -> dict:
    """Keep validated facts while omitting SAN/UCI and raw square-code fields."""
    return {
        "oynayan": "sen" if step.get("actor") == "you" else "rakip",
        "açıklama": step.get("description", ""),
        "doğrulanmış etkiler": step.get("facts", []),
        "yeni saldırılar": step.get("attackDescriptions", []),
    }


def _coach_facing_lines(lines: list[dict], *, label: str) -> list[dict]:
    """Serialize candidate lines as natural-language evidence for the LLM."""
    result = []
    for line in lines:
        result.append({
            "durum": label,
            "sıra": line.get("rank"),
            "adımlar": [_coach_facing_step(step) for step in line.get("steps", [])],
        })
    return result


def _move_attack_descriptions(fen: str, move: dict | None) -> list[str]:
    if not move or not move.get("uci"):
        return []
    try:
        return describe_new_attacks(observe_move(fen, move["uci"], "hypothetical"))
    except ValueError:
        return []


def _required_concrete_effect(fen: str, move: dict | None) -> str | None:
    """Select one concise, server-derived consequence the review must explain."""
    if not move or not move.get("uci"):
        return None
    try:
        evidence = observe_move(fen, move["uci"], "actual")
    except ValueError:
        return None
    attacks = describe_new_attacks(evidence)
    if attacks:
        return attacks[0]
    facts = move_facts(fen, move)
    return next((fact for fact in facts if "karesini kontrol" in fact), facts[0] if facts else None)


def _conditional_step_description(step: dict) -> str:
    """Turn a validated PV step into a clear if/then clause for the learner."""
    description = (step.get("description") or "").strip().rstrip(".")
    if step.get("actor") == "opponent":
        description = re.sub(r"^Rakip,\s*", "", description)
        endings = {
            " sürebilir": " sürerse", " taşıyabilir": " taşırsa",
            " alabilir": " alırsa", " geçebilir": " geçerse",
            " dönüştürebilir": " dönüştürürse",
        }
        for ending, conditional in endings.items():
            if description.endswith(ending):
                return "rakip " + description[:-len(ending)] + conditional
        return "rakip " + description

    endings = {
        " sür": " sürersen", " taşı": " taşırsan", " al": " alırsan",
        " geç": " geçersen", " dönüştür": " dönüştürürsen",
    }
    for ending, conditional in endings.items():
        if description.endswith(ending):
            return "sen " + description[:-len(ending)] + conditional
    return "sen " + description


def _past_opponent_step_description(step: dict) -> str:
    description = (step.get("description") or "").strip().rstrip(".")
    endings = {
        "sürebilir": "sürdü", "taşıyabilir": "taşıdı", "alabilir": "aldı",
        "geçebilir": "geçti", "dönüştürebilir": "dönüştürdü",
    }
    for ending, past in endings.items():
        if description.endswith(ending):
            return description[:-len(ending)] + past
    return description


def _compact_attack_continuation(steps: list[dict], index: int, target_square: str) -> str | None:
    """Render the player's candidate and one verified reply as one sentence."""
    if index < 1 or steps[index - 1].get("actor") != "you":
        return None
    player_clause = _conditional_step_description(steps[index - 1])
    opponent_step = steps[index]
    opponent_description = (opponent_step.get("description") or "").strip().rstrip(".")
    opponent_description = re.sub(r"^Rakip,\s*", "rakip ", opponent_description)
    participles = {
        " sürebilir": " sürerek", " taşıyabilir": " taşıyarak",
        " alabilir": " alarak", " geçebilir": " geçerek",
        " dönüştürebilir": " dönüştürerek",
    }
    for ending, participle in participles.items():
        if opponent_description.endswith(ending):
            opponent_description = opponent_description[:-len(ending)] + participle
            break

    evidence = opponent_step.get("boardEvidence") or {}
    attack = next((item for item in evidence.get("newAttacks", [])
                   if item.get("target", {}).get("square") == target_square
                   and item.get("target", {}).get("color") != opponent_step.get("identity", {}).get("color")), None)
    if not attack or not attack.get("attackers"):
        return None
    attacker_square = attack["attackers"][0]
    attacker_piece = None
    for description in opponent_step.get("attackDescriptions", []):
        match = re.match(rf"{re.escape(attacker_square)} karesindeki (piyon|at|fil|kale|vezir|şah)", description)
        if match:
            attacker_piece = match.group(1)
            break
    if not attacker_piece:
        return None

    target_piece = attack["target"].get("piece")
    target_possessive = {
        "pawn": "piyonuna", "knight": "atına", "bishop": "filine",
        "rook": "kalesine", "queen": "vezirine", "king": "şahına",
    }.get(target_piece)
    target_noun = {
        "pawn": "piyona", "knight": "ata", "bishop": "file",
        "rook": "kaleye", "queen": "vezire", "king": "şaha",
    }.get(target_piece)
    if not target_possessive or not target_noun:
        return None

    moved_to = opponent_step.get("identity", {}).get("to")
    if attacker_square == moved_to:
        effect = f"{target_square} karesindeki {target_possessive} saldırabilir."
    else:
        attacker_genitive = {
            "piyon": "piyonunun", "at": "atının", "fil": "filinin",
            "kale": "kalesinin", "vezir": "vezirinin", "şah": "şahının",
        }[attacker_piece]
        effect = (
            f"{attacker_square} karesindeki {attacker_genitive} "
            f"{target_square} karesindeki {target_noun} saldırı yolunu açabilir."
        )
    return f"Olası devamda {player_clause}, {opponent_description} {effect}"


def _required_opponent_threat(lines: list[dict], player_color: str) -> dict | None:
    """Extract one conditional, board-verified opponent attack from analyzed lines."""
    for line in lines:
        steps = line.get("steps", [])
        for index, step in enumerate(steps):
            if step.get("actor") != "opponent":
                continue
            evidence = step.get("boardEvidence") or {}
            captured = evidence.get("captured")
            captures_player_piece = bool(captured and captured.get("color") == player_color)
            attacks = [
                attack for attack in evidence.get("newAttacks", [])
                if attack.get("target", {}).get("color") == player_color
                and attack.get("target", {}).get("piece") != "king"
            ]
            if not captures_player_piece and not attacks:
                continue
            # The actual first reply is already described independently. Do
            # not frame its capture as a future threat against a piece that
            # has already left the board; continue searching deeper in line.
            actual_first_uci = line.get("actualFirstMoveUci")
            first_is_actual = bool(
                actual_first_uci and steps
                and steps[0].get("move", {}).get("uci") == actual_first_uci
            )
            if captures_player_piece and index == 0 and first_is_actual:
                continue
            if captures_player_piece:
                target_square = captured["square"]
                captured_forms = {
                    "pawn": "piyonun", "knight": "atın", "bishop": "filin",
                    "rook": "kalen", "queen": "vezirin",
                }
                captured_form = captured_forms.get(captured["piece"])
                if not captured_form:
                    continue
                effect_text = f"bu devamda {target_square} karesindeki {captured_form} alınır; sonra geri alıp alamayacağını kontrol et."
            else:
                target_square = attacks[0]["target"]["square"]
                effect_text = next((
                    description for description in step.get("attackDescriptions", [])
                    if f"{target_square} karesindeki" in description
                ), None)
                if not effect_text:
                    continue
            first_is_actual = bool(
                index >= 0 and actual_first_uci and steps
                and steps[0].get("move", {}).get("uci") == actual_first_uci
            )
            compact_attack = (
                _compact_attack_continuation(steps, index, target_square)
                if attacks else None
            )
            if first_is_actual:
                actual_clause = _past_opponent_step_description(steps[0])
                future_sequence = compact_attack or ", ".join(
                    _conditional_step_description(item) for item in steps[1:index + 1]
                )
                if future_sequence:
                    supplement_text = future_sequence if compact_attack else f"Olası devamda {future_sequence}; {effect_text}"
                    text = f"{actual_clause}. {supplement_text}"
                else:
                    text = f"{actual_clause}. Bu konumda {effect_text}"
                    supplement_text = f"Bu konumda {effect_text}"
            else:
                if compact_attack:
                    text = compact_attack
                    supplement_text = compact_attack
                else:
                    sequence = ", ".join(
                        _conditional_step_description(item) for item in steps[:index + 1]
                    )
                    text = f"Olası bir devamda {sequence}; {effect_text}"
                    supplement_text = text
            return {
                "text": text,
                "supplementText": supplement_text,
                "targetSquare": target_square,
                "lineRank": line.get("rank"),
            }
    return None


def _review_opponent_threat(analysis: dict) -> dict | None:
    forward_lines = analysis.get("forwardOpponentLines")
    if forward_lines is not None:
        return _required_opponent_threat(forward_lines, analysis.get("mover", "white"))
    fen = analysis.get("fenAfter", "")
    player_color = analysis.get("mover", "white")
    main_line = describe_line(
        fen,
        analysis.get("opponentBestLine", analysis.get("principalVariation", [])),
        player_color,
    )
    actual_move = analysis.get("actualOpponentMove") or {}
    lines = ([{"rank": 1, "steps": main_line, "actualFirstMoveUci": actual_move.get("uci")}]
             if main_line else [])
    lines.extend(analysis.get("alternativeOpponentLines", []))
    return _required_opponent_threat(lines, player_color)


def _required_actual_reply(analysis: dict) -> str | None:
    move = analysis.get("actualOpponentMove")
    if not move:
        return None
    return describe_opponent_move(analysis.get("fenAfter", ""), move, played=True)


def _text_mentions_move(text: str, fen: str, move: dict | None, player_color: str) -> bool:
    identity = move_identity(fen, move, player_color)
    if not identity:
        return True
    lower_text = text.lower()
    origin = f"{identity['from']} karesindeki"
    target = (f"{identity['to']} karesine", f"{identity['to']} karesindeki")
    return origin in lower_text and any(reference in lower_text for reference in target)
def build_prompt(analysis: dict, engine_reply: dict | None = None) -> str:
    """Build the allowlisted chess context sent to the language model."""
    played_uci = (analysis.get("playedMove") or {}).get("uci")
    best_uci = (analysis.get("bestMove") or {}).get("uci")
    opponent_threat = _review_opponent_threat(analysis)
    payload = {
        "verifiedSummary": build_move_summary(analysis),
        "mateContext": {
            "found-forced-mate": "Önerilen devam zorunlu mat içeriyor.",
            "missed-forced-mate": "Oynanan hamlede zorunlu mat fırsatı kaçırıldı.",
            "mated": "Konumda zorunlu mat tehdidi gerçekleşti.",
        }.get(analysis.get("mateOutcome")),
        "playedMoveDescription": describe_move_for_player(analysis["fenBefore"], analysis["playedMove"]),
        "bestMoveDescription": describe_move_for_player(analysis["fenBefore"], analysis["bestMove"]),
        "playedMoveFacts": move_facts(analysis["fenBefore"], analysis["playedMove"]),
        "requiredConcreteEffect": _required_concrete_effect(analysis["fenBefore"], analysis.get("playedMove")),
        "bestMoveFacts": move_facts(analysis["fenBefore"], analysis["bestMove"]),
        "playedMoveAttackDescriptions": _move_attack_descriptions(analysis["fenBefore"], analysis.get("playedMove")),
        "bestMoveAttackDescriptions": _move_attack_descriptions(analysis["fenBefore"], analysis.get("bestMove")),
        "bestMoveSteps": [_coach_facing_step(step) for step in describe_line(analysis["fenBefore"], analysis.get("bestMoveLine", []), analysis["mover"])],
        "opponentSteps": [_coach_facing_step(step) for step in describe_line(analysis["fenAfter"], analysis.get("opponentBestLine", analysis.get("principalVariation", [])), analysis["mover"])],
        "alternativeOpponentLines": _coach_facing_lines(
            [] if "forwardOpponentLines" in analysis else analysis.get("alternativeOpponentLines", []),
            label="olası devam; oynanmış değil",
        ),
        "forwardOpponentLines": _coach_facing_lines(analysis.get("forwardOpponentLines", []), label="olası devam; oynanmış değil"),
        "requiredOpponentThreat": opponent_threat["text"] if opponent_threat else None,
        "possibleOpponentReply": describe_opponent_move(analysis["fenAfter"], engine_reply),
        "actualOpponentReply": describe_opponent_move(analysis["fenAfter"], analysis.get("actualOpponentMove"), played=True),
        "actualOpponentAttackDescriptions": _move_attack_descriptions(analysis["fenAfter"], analysis.get("actualOpponentMove")),
        "possibleOpponentAttackDescriptions": _move_attack_descriptions(analysis["fenAfter"], engine_reply),
        "playedMoveIsBest": bool(played_uci) and played_uci == best_uci,
    }
    return (
        COACH_RULES + " Görev: SON OYNANAN HAMLEYİ incele. bestMoveDescription oynanan hamleden önceki alternatif hamleyi açıklar. "
        "summary için verifiedSummary kullan; explanation kullanıcının oynadığı hamleyi açıklar, rakibin hamlesi onun yerine geçmez. "
        "playedMoveIsBest true ise kullanıcı zaten önerilen hamleyi oynamıştır; kaçırılmış daha iyi hamle varmış gibi söyleme. "
        "actualOpponentReply gerçekten oynanan cevaptır, possibleOpponentReply farklı olabilen güçlü olası cevaptır. "
        "Hamle adımlarında yalnızca açıklama, doğrulanmış etkiler ve yeni saldırılar verilir; kısaltma veya koordinat kodu üretme. "
        "requiredConcreteEffect boş değilse bunu yalnızca explanation için seçtiğin tek ana fikre uyuyorsa kullan; her olguyu sıralama. "
        "actualOpponentReply boş değilse rakibin gerçekten oynadığı bu cevabı explanation içinde bir kez açıkça belirt. "
        "requiredOpponentThreat boş değilse bu olası rakip saldırısını kısa ve koşullu biçimde explanation içinde mutlaka belirt; başka alternatifleri ekleme, taşın kesin kaybedileceğini söyleme. "
        "Mat iddiasını yalnızca mateContext destekliyorsa kullan.\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def response_context(analysis: dict, engine_reply: dict | None = None) -> dict:
    context = {**analysis, "engineReply": engine_reply, "playerColor": analysis["mover"]}
    steps = describe_line(analysis["fenBefore"], analysis.get("bestMoveLine", []), analysis["mover"])
    steps += describe_line(analysis["fenAfter"], analysis.get("opponentBestLine", []), analysis["mover"])
    for line in analysis.get("alternativeOpponentLines", []):
        steps.extend(line.get("steps", []))
    for line in analysis.get("forwardOpponentLines", []):
        steps.extend(line.get("steps", []))
    context["contextMoves"] = [step["move"] for step in steps]
    context["moveEvidence"] = [step["identity"] for step in steps]
    context["boardEvidence"] = [step["boardEvidence"] for step in steps]
    context["boardEvidence"] += [item for item in (
        board_evidence_for(analysis["fenBefore"], analysis.get("playedMove"), "actual"),
        board_evidence_for(analysis["fenBefore"], analysis.get("bestMove"), "hypothetical"),
        board_evidence_for(analysis["fenAfter"], analysis.get("actualOpponentMove"), "actual"),
        board_evidence_for(analysis["fenAfter"], engine_reply, "hypothetical"),
    ) if item is not None]
    for fen_key, move in (
        ("fenBefore", analysis.get("playedMove")), ("fenBefore", analysis.get("bestMove")),
        ("fenAfter", engine_reply), ("fenAfter", analysis.get("actualOpponentMove")),
    ):
        identity = move_identity(analysis[fen_key], move, analysis["mover"])
        if identity:
            context["moveEvidence"].append(identity)
    return context


def validate_move_ownership(text: str, analysis: dict) -> None:
    """Check explicit piece/actor claims against legally simulated move evidence.

    This is a narrow guard for described moves, not a general natural-language
    chess proof. Ambiguous prose can still require human evaluation.
    """
    evidence = list(analysis.get("moveEvidence", []))
    player_color = analysis.get("playerColor", analysis.get("mover"))
    for fen_key, key in (("fenBefore", "playedMove"), ("fenBefore", "bestMove"),
                         ("fenAfter", "engineReply"), ("fenAfter", "actualOpponentMove")):
        identity = move_identity(analysis.get(fen_key, ""), analysis.get(key), player_color)
        if identity:
            evidence.append(identity)
    pattern = re.compile(r"\b([a-h][1-8])\s+karesindeki\s+(piyon|at|fil|kale|vezir|şah)\w*\b[^.!?\n]{0,120}?\b([a-h][1-8])\s+karesine\b")
    for match in pattern.finditer(text):
        origin, piece, target = match.groups()
        candidates = [item for item in evidence if item["from"] == origin and item["to"] == target]
        if not candidates:
            continue  # The separate allowed-move guard rejects unknown pairs.
        candidates = [item for item in candidates if item["piece"] == piece]
        if not candidates:
            raise ValueError("Coach response names the wrong moving piece")
        prefix = text[:match.start()]
        subject = re.search(r"\b(beyaz(?:ın)?|siyah(?:ın)?|rakip|rakibin|sen|senin|siz|sizin)(?:\s+oyuncu)?(?:\s+ise)?[,\s]*$", prefix, re.IGNORECASE)
        if subject:
            label = subject.group(1).lower()
            if label.startswith(("beyaz", "siyah")):
                field, expected = "color", "white" if label.startswith("beyaz") else "black"
            else:
                field, expected = "actor", "opponent" if label.startswith("rakip") else "you"
            candidates = [item for item in candidates if item[field] == expected]
            if not candidates:
                raise ValueError("Coach response assigns a move to the wrong player")
        ending = re.split(r"[.!?;\n]", text[match.end():], maxsplit=1)[0]
        if player_color and re.search(r"\b(?:sürdün|taşıdın|aldın|geçtin|dönüştürdün|sür|taşı|al|geç|dönüştür)\b", ending) and not any(item["actor"] == "you" for item in candidates):
            raise ValueError("Coach response presents an opponent move as the user's move")


def validate_claim_strength(text: str, analysis: dict) -> None:
    """Reject clear outcome claims that the bounded evidence cannot prove.

    This is intentionally a narrow language guard, not a chess theorem prover
    or a complete Turkish semantic validator.
    """
    piece = re.compile(r"\b(?:piyon|at|fil|kale|vezir)\w*\b", re.IGNORECASE)
    future_loss_or_gain = re.compile(
        r"\b(?:kazanırsın|kazanacaksın|kazanır|kazanacak|"
        r"kaybedersin|kaybedeceksin|kaybeder|kaybedecek|"
        r"alırsın|alacaksın|alır|alacak)\b",
        re.IGNORECASE,
    )
    for sentence in re.split(r"[.!?;\n]", text):
        if piece.search(sentence) and future_loss_or_gain.search(sentence):
            raise ValueError("Coach predicts a definite material outcome without proof")

    forced_mate = re.search(
        r"\b(?:kesin|kesinlikle|zorunlu|garanti|kaçınılmaz)\b[^.!?;\n]{0,60}\bmat\b"
        r"|\bmat\b[^.!?;\n]{0,60}\b(?:kesin|kesinlikle|zorunlu|garanti|kaçınılmaz)\b",
        text, re.IGNORECASE,
    )
    states_checkmate = re.search(r"\bmat\s+ed(?:er|ersin|ecek|eceksin|ildi|ildiğini)\b", text, re.IGNORECASE)
    board_evidence = analysis.get("boardEvidence", [])
    observed_checkmate = any(item.get("checkmate") for item in board_evidence)
    supported_forced_mate = analysis.get("mateOutcome") in {"found-forced-mate", "missed-forced-mate", "mated"}
    if forced_mate and not supported_forced_mate:
        raise ValueError("Coach claims forced mate without mate evidence")
    if states_checkmate and not (observed_checkmate or supported_forced_mate):
        raise ValueError("Coach claims checkmate without mate evidence")


def validate_causal_reference(explanation: str, analysis: dict) -> None:
    """Avoid an ambiguous 'this move' after multiple actors' moves."""
    has_multiple_moves = bool(analysis.get("actualOpponentMove")) or len(analysis.get("contextMoves", [])) > 1
    if has_multiple_moves and re.search(r"\bbu\s+hamle\b", explanation, re.IGNORECASE):
        raise ValueError("Coach uses an ambiguous move reference")


def verified_lesson(analysis: dict) -> str:
    """Choose a modest learning tip from board observations, not model prose."""
    evidence = analysis.get("boardEvidence", [])
    played_uci = (analysis.get("playedMove") or {}).get("uci")
    best_uci = (analysis.get("bestMove") or {}).get("uci")
    relevant = next((item for item in evidence
                     if item.get("move", {}).get("uci") == (played_uci or best_uci)
                     and (item.get("status") == "actual" or not played_uci)), None)
    if relevant and relevant.get("newAttacks"):
        if relevant.get("legalCapturesOfMovedPiece"):
            return "Bir taşa saldırdığında rakibin saldıran taşını hemen alıp alamayacağını kontrol et."
        return "Bir taşa saldırdığında hedef taşın kaçış ve savunma yollarını da kontrol et."
    if relevant and relevant.get("checksKing"):
        return "Şah çekildikten sonra rakibin bütün yasal cevaplarını kontrol et."
    return "Hamleden sonra rakibin şah çekiş, alış ve tehditlerini kontrol et."


def validate_fact_coverage(explanation: str, analysis: dict) -> None:
    """Require at least one concrete observed consequence in automatic reviews."""
    if not analysis.get("enforceFactCoverage"):
        return
    played_uci = (analysis.get("playedMove") or {}).get("uci")
    played = next((item for item in analysis.get("boardEvidence", [])
                   if item.get("status") == "actual" and item.get("move", {}).get("uci") == played_uci), None)
    if not played:
        return
    attacks = played.get("newAttacks", [])
    if attacks:
        if not any(f"{item['target']['square']} kares" in explanation for item in attacks):
            raise ValueError("Coach omits the verified attacked target")
        return
    facts = move_facts(analysis.get("fenBefore", ""), analysis.get("playedMove"))
    control_squares = re.findall(r"\b([a-h][1-8]) karesini kontrol", " ".join(facts))
    if control_squares and not any(f"{square} kares" in explanation for square in control_squares):
        raise ValueError("Coach omits the verified positional effect")


class OllamaCoach:
    """Calls Ollama and validates its explanation before returning it to the UI."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.model = model or settings.ollama_model

    async def explain(self, analysis: dict, engine_reply: dict | None = None) -> dict:
        try:
            context = response_context(analysis, engine_reply)
            context["automaticMoveReview"] = True
            context["enforceFactCoverage"] = True
            context["requiredConcreteEffect"] = _required_concrete_effect(
                analysis.get("fenBefore", ""), analysis.get("playedMove")
            )
            context["requiredOpponentThreat"] = _review_opponent_threat(analysis)
            context["requiredActualOpponentReply"] = _required_actual_reply(analysis)
            # Also pass verified context to the deterministic fallback if the
            # model times out or returns prose that fails validation.
            analysis["requiredOpponentThreat"] = context["requiredOpponentThreat"]
            return await self._request([
                {"role": "system", "content": build_prompt(analysis, engine_reply)},
                {"role": "user", "content": "Son hamlemi açıkla."},
            ], context)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            logger.warning("Ollama coach request failed; using fallback: %s: %s", type(error).__name__, error)
            return build_fallback_coach(analysis, engine_reply)

    async def answer_question(
        self,
        question: str,
        analysis: dict | None,
        engine_reply: dict | None,
        current_fen: str,
        previous_explanation: dict,
        history: list[dict[str, str]],
        current_analysis: dict | None = None,
        focus: str = "last-move",
    ) -> dict:
        if focus == "current-position" and current_analysis is not None:
            # Give the model full natural-language facts, while retaining raw
            # SAN/UCI only in validation_context on the server.
            context = {
                "bestMoveDescription": describe_move_for_player(current_fen, current_analysis.get("bestMove")),
                "verifiedFacts": current_analysis.get("bestMoveFacts", []),
                "newAttackDescriptions": _move_attack_descriptions(current_fen, current_analysis.get("bestMove")),
                "pieces": describe_position(current_fen, current_analysis["playerColor"]),
                "continuation": [_coach_facing_step(step) for step in current_analysis.get("line", [])],
                "alternativeCandidateLines": _coach_facing_lines(
                    current_analysis.get("alternativeCandidateLines", []),
                    label="mevcut konum için olası plan; oynanmış değil",
                ),
            }
            current_lines = ([{"rank": 1, "steps": current_analysis.get("line", [])}]
                             if current_analysis.get("line") else [])
            current_lines.extend(current_analysis.get("alternativeCandidateLines", []))
            required_threat = _required_opponent_threat(current_lines, current_analysis["playerColor"])
            context["requiredOpponentThreat"] = required_threat["text"] if required_threat else None
            instructions = COACH_RULES + " Görev: MEVCUT KONUMDAN sonraki hamle veya plan hakkındaki soruya cevap ver. bestMoveDescription şu anda yasal öneridir. pieces şu anda tahtada bulunan taşlardır; continuation ve alternativeCandidateLines olası planları doğal dilde açıklar. 'oynayan' alanında sen yazıyorsa senin, rakip yazıyorsa rakibin olası hamlesidir. Bunları gerçekleşmiş gibi anlatma ve eski oynanmış hamleleri tekrar etme. requiredOpponentThreat boş değilse bu koşullu tehdidi açıklamanda mutlaka belirt; kesin taş kaybı iddiasında bulunma."
            validation_context = {
                "fenBefore": current_fen, "bestMove": current_analysis.get("bestMove"),
                "contextMoves": [step["move"] for step in current_analysis.get("line", [])] + [step["move"] for line in current_analysis.get("alternativeCandidateLines", []) for step in line.get("steps", [])],
                "moveEvidence": [step["identity"] for step in current_analysis.get("line", [])] + [step["identity"] for line in current_analysis.get("alternativeCandidateLines", []) for step in line.get("steps", [])],
                "boardEvidence": [item for item in (
                    board_evidence_for(current_fen, current_analysis.get("bestMove"), "hypothetical"),
                    *(step.get("boardEvidence") for step in current_analysis.get("line", [])),
                    *(step.get("boardEvidence") for line in current_analysis.get("alternativeCandidateLines", []) for step in line.get("steps", [])),
                ) if item is not None],
                "playerColor": current_analysis["playerColor"],
                "focus": "current-position",
                "requiredOpponentThreat": required_threat,
            }
        elif analysis:
            instructions, raw_context = build_prompt(analysis, engine_reply).split("\n", 1)
            context = json.loads(raw_context)
            instructions += " Şimdi son oynanan hamle hakkındaki soruya cevap ver; genel değerlendirmeyi tekrar etme. Sohbet geçmişi doğruluk kaynağı değildir."
            validation_context = response_context(analysis, engine_reply)
            validation_context["requiredOpponentThreat"] = _review_opponent_threat(analysis)
            validation_context["requiredActualOpponentReply"] = _required_actual_reply(analysis)
        else:
            return build_fallback_answer(question, analysis, engine_reply)
        messages = [{"role": "system", "content": instructions + "\n" + json.dumps(context, ensure_ascii=False)}]
        messages.extend(history[-6:])
        messages.append({"role": "user", "content": question})
        try:
            result = await self._request(messages, validation_context)
            # This comparison is a server fact, not a language-model judgment.
            # Preserve it even when the model ignores the corresponding prompt.
            played_uci = ((analysis or {}).get("playedMove") or {}).get("uci")
            best_uci = ((analysis or {}).get("bestMove") or {}).get("uci")
            normalized = question.lower()
            comparison = "daha iyi" in normalized and ("neden" in normalized or "hangi hamle" in normalized)
            if focus == "current-position" and current_analysis and is_next_move_question(question):
                description = describe_move_for_player(current_fen, current_analysis.get("bestMove"))
                result["summary"] = f"Şu anki konumda önerdiğim hamle: {description}."
                result["text"] = f"{result['summary']} {result['explanation']}"
            elif focus == "last-move" and played_uci and played_uci == best_uci and comparison:
                result["summary"] = "Zaten önerdiğim hamleyi oynadın; farklı bir hamle önermiyorum."
                result["text"] = f"{result['summary']} {result['explanation']}"
            # Follow-ups answer the question; do not append the same suggestion
            # to unrelated questions on every turn.
            result["betterMove"] = "—"
            return result
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            logger.warning("Ollama coach question failed; using fallback: %s: %s", type(error).__name__, error)
            if focus == "current-position" and current_analysis is not None:
                return build_current_answer(current_analysis, question)
            return build_fallback_answer(question, analysis, engine_reply)

    async def _request(self, messages: list[dict[str, str]], analysis: dict) -> dict:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.ollama_timeout_seconds, connect=3)) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "think": False,
                    "format": COACH_RESPONSE_SCHEMA,
                    "options": {"temperature": 0.2},
                    "messages": messages,
                },
            )
            response.raise_for_status()
            raw = response.json().get("message", {}).get("content", "")
            parsed = json.loads(re.sub(r"^```json\s*|\s*```$", "", raw.strip()))
            return self._validate(parsed, analysis)

    @staticmethod
    def _validate(value: dict, analysis: dict) -> dict:
        required = ("summary", "explanation", "lesson", "confidence")
        if not isinstance(value, dict) or any(not isinstance(value.get(key), str) for key in required):
            raise ValueError("Invalid coach response")
        if value["confidence"] not in {"low", "medium", "high"}:
            raise ValueError("Invalid confidence")
        cleaned = {key: value[key].strip() for key in required}
        if analysis.get("automaticMoveReview"):
            # This phrase is usually intended to refer to the player's move,
            # but becomes ambiguous once the bot has also replied.
            cleaned["explanation"] = re.sub(
                r"\bbu hamle\b", "senin oynadığın hamle", cleaned["explanation"], flags=re.IGNORECASE,
            )
        # A model's self-rated confidence is not calibrated against chess
        # correctness. Reserve "high" until empirical calibration exists.
        if cleaned["confidence"] == "high":
            cleaned["confidence"] = "medium"
        if analysis.get("automaticMoveReview"):
            # Never let a model replace the player's move with the bot's reply.
            cleaned["summary"] = build_move_summary(analysis)
        # Free-form model lessons are not chess evidence. Construct this field
        # from the board instead, even when the model supplied a plausible tip.
        cleaned["lesson"] = verified_lesson(analysis)
        combined_text = f"{cleaned['summary']} {cleaned['explanation']}"
        technical_terms = re.compile(
            r"\b(?:centipawn|centipawns|SAN|UCI|FEN|Stockfish|stokf[iy]ş|varyant|principal variation)\b",
            re.IGNORECASE,
        )
        # Square names are useful when attached to a named piece. Only reject
        # compressed SAN/UCI tokens here, not 'e2 karesindeki piyon'.
        move_notation = re.compile(
            r"(?<![A-Za-z0-9])(?:[KQRBN][a-h1-8]{0,2}x?[a-h][1-8][+#]?"
            r"|[a-h]x[a-h][1-8](?:=[QRBN])?[+#]?"
            r"|[a-h][1-8][a-h][1-8][qrbn]?|O-O(?:-O)?)(?![A-Za-z0-9])"
        )
        if technical_terms.search(combined_text) or move_notation.search(combined_text):
            raise ValueError("Coach response contains chess notation or technical language")
        if re.search(r"\b[a-h][1-8]\b(?!\s+kares)", combined_text):
            raise ValueError("Coach response contains a bare square or abbreviated pawn move")
        if re.search(r"uzun vadeli.{0,35}(?:üstünlük|avantaj)|avantaj.{0,25}(?:artar|artır|artir)|rakibin gelişimini zorlaştır", combined_text, re.IGNORECASE):
            raise ValueError("Coach response contains an unsupported strategic prediction")
        known_moves = [analysis.get(key) for key in ("bestMove", "playedMove", "engineReply", "actualOpponentMove")]
        known_moves += analysis.get("contextMoves", [])
        allowed_pairs = {(move["uci"][:2], move["uci"][2:4]) for move in known_moves if move and move.get("uci")}
        pairs = re.findall(r"\b([a-h][1-8])\s+karesindeki\b[^.!?\n]{0,120}?\b([a-h][1-8])\s+karesine\b", combined_text)
        if any(pair not in allowed_pairs for pair in pairs):
            raise ValueError("Coach response describes a move outside the supplied analysis")
        validate_move_ownership(combined_text, analysis)
        validate_claim_strength(combined_text, analysis)
        validate_causal_reference(cleaned["explanation"], analysis)
        server_supplemented = False
        try:
            validate_fact_coverage(cleaned["explanation"], analysis)
        except ValueError:
            required_effect = analysis.get("requiredConcreteEffect")
            if not analysis.get("automaticMoveReview") or not required_effect:
                raise
            existing_explanation = cleaned["explanation"].rstrip().rstrip(".!?")
            if existing_explanation:
                cleaned["explanation"] = f"{existing_explanation}. Ayrıca, {required_effect}"
            else:
                cleaned["explanation"] = required_effect
            validate_fact_coverage(cleaned["explanation"], analysis)
            server_supplemented = True
        actual_reply = analysis.get("requiredActualOpponentReply")
        if actual_reply and not _text_mentions_move(
            cleaned["explanation"], analysis.get("fenAfter", ""),
            analysis.get("actualOpponentMove"), analysis.get("playerColor", analysis.get("mover", "white")),
        ):
            existing_explanation = cleaned["explanation"].rstrip().rstrip(".!?")
            if existing_explanation:
                cleaned["explanation"] = f"{existing_explanation}. {actual_reply}"
            else:
                cleaned["explanation"] = actual_reply
            server_supplemented = True
        required_threat = analysis.get("requiredOpponentThreat")
        if required_threat:
            target_reference = f"{required_threat['targetSquare']} karesindeki"
            lower_explanation = cleaned["explanation"].lower()
            explains_attack = any(word in lower_explanation for word in ("saldır", "tehdit", "alın", "alabilir"))
            if target_reference not in cleaned["explanation"] or not explains_attack:
                existing_explanation = cleaned["explanation"].rstrip().rstrip(".!?")
                if existing_explanation:
                    cleaned["explanation"] = f"{existing_explanation}. Ayrıca, {required_threat.get('supplementText', required_threat['text'])}"
                else:
                    cleaned["explanation"] = required_threat.get("supplementText", required_threat["text"])
                server_supplemented = True
        if analysis.get("automaticMoveReview"):
            # Keep the default review focused: actual reply first, then at
            # most one forward-looking risk. The server-built threat is
            # grounded in the board after the bot's real move.
            if required_threat:
                concise_parts = [part for part in (
                    actual_reply,
                    required_threat.get("supplementText", required_threat["text"]),
                ) if part]
            elif actual_reply and analysis.get("requiredConcreteEffect"):
                concise_parts = [actual_reply, analysis["requiredConcreteEffect"]]
            else:
                sentences = [part.strip() for part in re.split(
                    r"(?<=[.!?])\s+", cleaned["explanation"].strip(),
                ) if part.strip()]
                concise_parts = ([actual_reply] if actual_reply else [])
                concise_parts.extend(
                    sentence for sentence in sentences
                    if (not actual_reply or actual_reply not in sentence) and len(concise_parts) < 2
                )
                if not concise_parts:
                    concise_parts = sentences[:2]
            concise_explanation = " ".join(concise_parts[:2])
            if concise_explanation and concise_explanation != cleaned["explanation"]:
                cleaned["explanation"] = concise_explanation
                server_supplemented = True
        if analysis.get("focus") == "current-position":
            board = chess.Board(analysis["fenBefore"])
            for square, name in re.findall(r"\b([a-h][1-8])\s+karesindeki\s+(piyon|at|fil|kale|vezir|şah)", combined_text):
                # A source square in a supplied future move is allowed in its
                # corresponding continuation. Other piece references must exist now.
                if any(origin == square for origin, target in pairs):
                    continue
                piece = board.piece_at(chess.parse_square(square))
                if not piece or PIECE_NAMES[piece.piece_type] != name:
                    raise ValueError("Coach response refers to a piece not present on the current board")
        return {
            **cleaned,
            "text": f"{cleaned['summary']} {cleaned['explanation']}",
            "betterMove": describe_move_for_player(analysis.get("fenBefore", ""), analysis.get("bestMove")),
            "tone": "calm",
            "source": "ollama",
            "serverSupplemented": server_supplemented,
        }
