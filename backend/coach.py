from __future__ import annotations

import chess
import re

from .position_evidence import compact_evidence, observe_move


PIECE_NAMES = {chess.PAWN: "piyon", chess.KNIGHT: "at", chess.BISHOP: "fil", chess.ROOK: "kale", chess.QUEEN: "vezir", chess.KING: "şah"}
PIECE_FORMS = {
    chess.PAWN: ("piyonunu", "piyonunla"),
    chess.KNIGHT: ("atını", "atınla"),
    chess.BISHOP: ("filini", "filinle"),
    chess.ROOK: ("kalesini", "kalenle"),
    chess.QUEEN: ("vezirini", "vezirinle"),
    chess.KING: ("şahını", "şahınla"),
}


def normalized_question(question: str) -> str:
    return question.lower().translate(str.maketrans("ıöüçşğ", "ioucsg"))


def describe_position(fen: str, player_color: str) -> dict[str, list[str]]:
    board = chess.Board(fen)
    pieces = {"you": [], "opponent": []}
    for square, piece in sorted(board.piece_map().items()):
        actor = "you" if (piece.color == chess.WHITE) == (player_color == "white") else "opponent"
        pieces[actor].append(f"{chess.square_name(square)} karesinde {PIECE_NAMES[piece.piece_type]}")
    return pieces


def is_next_move_question(question: str) -> bool:
    normalized = normalized_question(question)
    return any(phrase in normalized for phrase in (
        "sonraki", "siradaki", "simdi", "bundan sonra", "devam",
        "ne oynam", "ne oynay", "ne yapm", "ne yapay", "hamlem ne",
    )) or ("hangi hamle" in normalized and "vardi" not in normalized and "oynad" not in normalized)


def resolve_question_focus(question: str, previous_focus: str = "last-move") -> str:
    """Choose the board snapshot, retaining the topic for short follow-ups."""
    normalized = normalized_question(question)
    if is_next_move_question(question):
        return "current-position"
    if any(phrase in normalized for phrase in (
        "oynadigim", "oynadim", "son hamlem", "onceki", "kacirdim", "hangi hamle vardi",
    )):
        return "last-move"
    if any(phrase in normalized for phrase in ("neden", "hangi piyon", "hangi tas", "ne demek", "onerdig")):
        return previous_focus
    return "current-position"


def describe_move_for_player(fen: str, move_details: dict | None) -> str:
    """Name the exact piece and squares without using compressed move notation."""
    if not fen or not move_details:
        return "—"

    try:
        board = chess.Board(fen)
        move = chess.Move.from_uci(move_details["uci"])
        piece = board.piece_at(move.from_square)
        if piece is None or move not in board.legal_moves:
            return "—"
    except (KeyError, TypeError, ValueError):
        return "—"

    accusative, instrumental = PIECE_FORMS[piece.piece_type]
    origin = chess.square_name(move.from_square)
    target = chess.square_name(move.to_square)
    if board.is_castling(move):
        kingside = board.is_kingside_castling(move)
        rank = chess.square_rank(move.from_square) + 1
        rook_origin = f"{'h' if kingside else 'a'}{rank}"
        rook_target = f"{'f' if kingside else 'd'}{rank}"
        return (
            f"{'Kısa' if kingside else 'Uzun'} rok yap: şahını {origin} karesinden {target} karesine, "
            f"kaleni {rook_origin} karesinden {rook_target} karesine taşı"
        )

    captured = board.piece_at(move.to_square)
    captured_square = target
    if board.is_en_passant(move):
        captured = chess.Piece(chess.PAWN, not piece.color)
        captured_square = chess.square_name(move.to_square + (-8 if piece.color else 8))
    if captured:
        captured_form = PIECE_FORMS[captured.piece_type][0]
        description = f"{origin} karesindeki {instrumental} rakibin {captured_square} karesindeki {captured_form} al"
        if board.is_en_passant(move):
            description += f" ve {target} karesine geç"
    else:
        verb = "sür" if piece.piece_type == chess.PAWN else "taşı"
        description = f"{origin} karesindeki {accusative} {target} karesine {verb}"
    if move.promotion:
        promoted_forms = {chess.QUEEN: "vezire", chess.ROOK: "kaleye", chess.BISHOP: "file", chess.KNIGHT: "ata"}
        description += f" ve piyonunu {promoted_forms[move.promotion]} dönüştür"
    return description


def move_identity(fen: str, move_details: dict | None, player_color: str) -> dict | None:
    """Derive ownership from the legal position, never from model-written text."""
    if describe_move_for_player(fen, move_details) == "—":
        return None
    board = chess.Board(fen)
    move = chess.Move.from_uci(move_details["uci"])
    piece = board.piece_at(move.from_square)
    color = "white" if piece.color else "black"
    return {
        "uci": move.uci(), "from": chess.square_name(move.from_square),
        "to": chess.square_name(move.to_square), "piece": PIECE_NAMES[piece.piece_type],
        "color": color, "actor": "you" if color == player_color else "opponent",
    }


def build_move_summary(analysis: dict) -> str:
    """The played move and verdict are server facts, not LLM decisions."""
    description = describe_move_for_player(analysis.get("fenBefore", ""), analysis.get("playedMove"))
    verdicts = {
        "best": "Bu konumda en güçlü seçeneklerden birini oynadın.",
        "good": "Bu hamle iyi bir tercih.",
        "inaccuracy": "Bu konumda daha güçlü bir seçenek vardı.",
        "mistake": "Bu hamle konumunu zorlaştırdı; daha güçlü bir seçenek vardı.",
        "blunder": "Bu hamle konumunu belirgin biçimde zorlaştırdı; daha güçlü bir seçenek vardı.",
    }
    verdict = verdicts.get(analysis.get("classification"), "Hamlen değerlendirildi.")
    if description == "—":
        return verdict
    past_tense = {
        "sür": "sürdün", "taşı": "taşıdın", "al": "aldın", "geç": "geçtin",
        "dönüştür": "dönüştürdün", "yap": "yaptın",
    }
    played = re.sub(r"\b(?:sür|taşı|al|geç|dönüştür|yap)\b", lambda match: past_tense[match.group()], description)
    return f"{played}. {verdict}"


def describe_opponent_move(fen: str, move: dict | None, played: bool = False) -> str:
    description = describe_move_for_player(fen, move)
    if description == "—":
        return description
    board = chess.Board(fen)
    legal_move = chess.Move.from_uci(move["uci"])
    if board.is_capture(legal_move):
        piece = board.piece_at(legal_move.from_square)
        opponent_instrumental = {
            chess.PAWN: "piyonuyla", chess.KNIGHT: "atıyla", chess.BISHOP: "filiyle",
            chess.ROOK: "kalesiyle", chess.QUEEN: "veziriyle", chess.KING: "şahıyla",
        }
        description = description.replace(
            f"{PIECE_FORMS[piece.piece_type][1]} rakibin ",
            f"{opponent_instrumental[piece.piece_type]} ", 1,
        )
    description = description.replace("Kısa rok yap: ", "kısa rok yapıp ").replace("Uzun rok yap: ", "uzun rok yapıp ")
    prefix, verb = description.rsplit(" ", 1)
    endings = {
        "sür": ("sürebilir", "sürdü"), "taşı": ("taşıyabilir", "taşıdı"),
        "al": ("alabilir", "aldı"), "geç": ("geçebilir", "geçti"),
        "dönüştür": ("dönüştürebilir", "dönüştürdü"),
    }
    return f"Rakip, {prefix} {endings[verb][1 if played else 0]}."


def move_facts(fen: str, move_details: dict | None) -> list[str]:
    """Facts from legal board simulation, not guesses about strategic advantage."""
    if describe_move_for_player(fen, move_details) == "—":
        return []
    board = chess.Board(fen)
    move = chess.Move.from_uci(move_details["uci"])
    capture = board.is_capture(move)
    board.push(move)
    facts = []
    if board.is_checkmate():
        facts.append("Bu hamle rakibi mat eder.")
    elif board.is_check():
        facts.append("Bu hamle rakibin şahına saldırır; rakip şahını bu saldırıdan kurtarmalıdır.")
    if capture:
        facts.append("Bu hamle rakibin bir taşını alır; devamında rakibin geri alıp alamayacağını kontrol et.")
    central = sorted(board.attacks(move.to_square) & chess.SquareSet([chess.D4, chess.E4, chess.D5, chess.E5]))
    if central:
        squares = " ve ".join(f"{chess.square_name(square)} karesini" for square in central)
        moved_piece = board.piece_at(move.to_square)
        facts.append(f"{chess.square_name(move.to_square)} karesine gelen {PIECE_NAMES[moved_piece.piece_type]} {squares} kontrol eder.")
    return facts


def describe_new_attacks(evidence: dict) -> list[str]:
    """Name newly attacked pieces from the verified post-move board."""
    board = chess.Board(evidence["fenAfter"])
    target_forms = {
        chess.PAWN: "piyona", chess.KNIGHT: "ata", chess.BISHOP: "file",
        chess.ROOK: "kaleye", chess.QUEEN: "vezire", chess.KING: "şaha",
    }
    sentences = []
    for attack in evidence["newAttacks"]:
        target_square = attack["target"]["square"]
        target = board.piece_at(chess.parse_square(target_square))
        for attacker_square in attack["attackers"]:
            attacker = board.piece_at(chess.parse_square(attacker_square))
            sentences.append(
                f"{attacker_square} karesindeki {PIECE_NAMES[attacker.piece_type]}, "
                f"{target_square} karesindeki {target_forms[target.piece_type]} saldırıyor."
            )
    return sentences


def describe_line(fen: str, san_line: list[str], player_color: str) -> list[dict]:
    """Validate each step and attach the exact piece/squares in its own position."""
    try:
        board = chess.Board(fen)
    except ValueError:
        return []
    result = []
    for san in san_line[:6]:
        try:
            move = board.parse_san(san)
        except ValueError:
            break
        actor = "you" if (board.turn == chess.WHITE) == (player_color == "white") else "opponent"
        details = {"uci": move.uci(), "from": chess.square_name(move.from_square), "to": chess.square_name(move.to_square), "san": san}
        description = describe_move_for_player(board.fen(), details) if actor == "you" else describe_opponent_move(board.fen(), details)
        result.append({
            "actor": actor,
            "identity": move_identity(board.fen(), details, player_color),
            "move": details,
            "description": description,
            "facts": move_facts(board.fen(), details),
            "boardEvidence": compact_evidence(observe_move(board.fen(), move.uci(), "hypothetical")),
            "attackDescriptions": describe_new_attacks(observe_move(board.fen(), move.uci(), "hypothetical")),
        })
        board.push(move)
    return result


def build_current_answer(current: dict, question: str = "") -> dict:
    """A useful, legal recommendation even if the language model is unavailable."""
    if current.get("isGameOver"):
        text = "Oyun sona erdi; bu konumda oynanacak bir sonraki hamle yok."
    elif current.get("turn") != current.get("playerColor"):
        text = "Şu anda rakibin sırası. Rakibin hamlesinden sonra sonraki hamleni değerlendirebiliriz."
    elif current.get("bestMove"):
        description = describe_move_for_player(current["fen"], current["bestMove"])
        normalized = normalized_question(question)
        line = current.get("line", [])
        asks_about_opponent = "rakib" in normalized and any(word in normalized for word in ("ne yap", "tehdit", "dikkat", "cevap"))
        if asks_about_opponent and len(line) > 1 and line[1].get("attackDescriptions"):
            text = f"Değerlendirilen plan: {description}. Bundan sonra {line[1]['description'][0].lower() + line[1]['description'][1:]}"
            text += " " + " ".join(line[1]["attackDescriptions"])
            text += " Bu olası bir devam; rakibin kesin bu hamleyi oynayacağı veya bunun kesin bir tehdit olduğu anlamına gelmez."
            return {"text": text, "betterMove": "—", "source": "fallback", "tone": "calm"}
        if asks_about_opponent:
            for candidate in current.get("alternativeCandidateLines", []):
                tactical_indices = candidate.get("tacticalStepIndices", [])
                for index in tactical_indices:
                    step = candidate.get("steps", [])[index]
                    if step.get("actor") == "opponent":
                        details = " ".join(step.get("attackDescriptions", [])) or "Bu olası devamda şah, alış veya taş tehdidi bulunuyor."
                        return {
                            "text": f"Rakibin olası devamı: {step['description']} {details} Bu, kesin oynayacağı anlamına gelmez.",
                            "betterMove": "—", "source": "fallback", "tone": "calm",
                        }
        if asks_about_opponent and len(line) > 1:
            text = f"Değerlendirilen plan: {description}. Bundan sonra {line[1]['description'][0].lower() + line[1]['description'][1:]}"
            text += " Bu olası bir devam; rakibin kesin bu hamleyi oynayacağı anlamına gelmez."
            return {"text": text, "betterMove": "—", "source": "fallback", "tone": "calm"}
        text = f"Şu anki konumda önerdiğim hamle: {description}."
        facts = current.get("bestMoveFacts", [])
        if facts:
            text += " " + facts[0]
        if len(line) > 1:
            text += " " + line[1]["description"]
    else:
        text = "Mevcut konum için güvenilir bir hamle önerisi hazırlanamadı."
    return {"text": text, "betterMove": "—", "source": "fallback", "tone": "calm"}


def build_fallback_coach(analysis: dict, engine_reply: dict | None = None) -> dict:
    summary = build_move_summary(analysis)
    better_move = describe_move_for_player(analysis.get("fenBefore", ""), analysis.get("bestMove"))
    facts = move_facts(analysis.get("fenBefore", ""), analysis.get("playedMove"))
    board_evidence = None
    try:
        board_evidence = observe_move(analysis["fenBefore"], analysis["playedMove"]["uci"], "actual")
    except (KeyError, TypeError, ValueError):
        pass
    attack_facts = describe_new_attacks(board_evidence) if board_evidence else []
    actual_reply = analysis.get("actualOpponentMove")
    actual_reply_text = describe_opponent_move(
        analysis.get("fenAfter", ""), actual_reply or engine_reply, played=bool(actual_reply),
    )
    forward_threat = analysis.get("requiredOpponentThreat")
    if forward_threat:
        # Keep the fallback readable too: one actual reply, then one verified
        # conditional risk from the board after that reply.
        explanation = actual_reply_text if actual_reply_text != "—" else ""
        threat_text = forward_threat.get("supplementText", forward_threat.get("text", ""))
        if threat_text:
            explanation += (" " if explanation else "") + threat_text
    else:
        explanation = " ".join(attack_facts[:1] or facts[:1])
    if board_evidence and not actual_reply and board_evidence["legalCapturesOfMovedPiece"]:
        capture = {"uci": board_evidence["legalCapturesOfMovedPiece"][0]}
        reply_description = describe_opponent_move(board_evidence["fenAfter"], capture)
        if reply_description != "—":
            explanation += (" " if explanation else "") + reply_description
    if not forward_threat and actual_reply_text != "—":
        explanation += (" " if explanation else "") + actual_reply_text
    for candidate in ([] if analysis.get("forwardOpponentLines") is not None else analysis.get("alternativeOpponentLines", [])):
        for index in candidate.get("tacticalStepIndices", []):
            steps = candidate.get("steps", [])
            if index >= len(steps) or steps[index].get("actor") != "opponent":
                continue
            step = steps[index]
            details = " ".join(step.get("attackDescriptions", []))
            if details:
                explanation += (" " if explanation else "") + f"Rakibin başka bir olası devamı: {step['description']} {details}"
                break
        else:
            continue
        break
    if not explanation:
        explanation = "Ayrıntılı yorumu şu an açıklayamıyorum. Hamleyi tahtada karşılaştırabiliriz."
    return {
        "summary": summary,
        "explanation": explanation,
        "lesson": "Her hamleden önce rakibinin taşlarına ve oluşturabileceği tehditlere kısaca bak.",
        "confidence": "low",
        "text": f"{summary} {explanation}",
        "betterMove": better_move,
        "tone": "calm",
        "source": "fallback",
    }


def build_fallback_answer(question: str, analysis: dict | None, engine_reply: dict | None = None) -> dict:
    """Be explicit about unavailable coaching instead of pretending to answer."""
    if not analysis:
        text = "Henüz değerlendirilecek bir hamlen yok. İlk hamleni oyna; sonra o konum üzerinden konuşalım."
    else:
        normalized = question.lower()
        move = describe_move_for_player(analysis.get("fenBefore", ""), analysis.get("bestMove"))
        played_uci = (analysis.get("playedMove") or {}).get("uci")
        best_uci = (analysis.get("bestMove") or {}).get("uci")
        same_move = bool(played_uci) and played_uci == best_uci
        comparison = "daha iyi" in normalized and ("neden" in normalized or "hangi hamle" in normalized)
        if same_move and comparison:
            text = "Zaten önerdiğim hamleyi oynadın; farklı bir hamle önermiyorum."
            facts = move_facts(analysis["fenBefore"], analysis.get("playedMove"))
            if facts:
                text += " " + facts[0]
        elif "neden" in normalized:
            text = "Ayrıntılı yorumu şu an açıklayamıyorum."
            if move != "—":
                text += f" Son hamlenden önceki konumda değerlendirilen alternatif: {move}."
                facts = move_facts(analysis["fenBefore"], analysis.get("bestMove"))
                if facts:
                    text += " " + facts[0]
        elif any(word in normalized for word in ("hangi hamle", "öner", "hangi piyon")) and move != "—":
            text = f"Son hamlenden önceki konum için önerim: {move}. Ayrıntılı açıklama şu an kullanılamıyor."
        else:
            text = "Soruna özel bir koç yanıtı şu an hazırlanamadı. Biraz sonra tekrar deneyebilirsin."
        if engine_reply:
            reply = describe_opponent_move(analysis.get("fenAfter", ""), engine_reply)
            if reply != "—":
                text += " " + reply
        asks_about_opponent = "rakib" in normalized and any(
            word in normalized for word in ("ne yap", "tehdit", "dikkat", "cevap")
        )
        if asks_about_opponent:
            for candidate in analysis.get("alternativeOpponentLines", []):
                for index in candidate.get("tacticalStepIndices", []):
                    steps = candidate.get("steps", [])
                    if index >= len(steps) or steps[index].get("actor") != "opponent":
                        continue
                    step = steps[index]
                    details = " ".join(step.get("attackDescriptions", []))
                    if details:
                        text += f" Rakibin başka bir olası devamı: {step['description']} {details}"
                        break
                else:
                    continue
                break
    return {"text": text, "betterMove": "—", "source": "fallback", "tone": "calm"}
