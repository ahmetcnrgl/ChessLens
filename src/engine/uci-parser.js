export function parseInfoLine(line) {
  if (!line.startsWith("info ")) return null;

  const depth = line.match(/\bdepth (\d+)/)?.[1];
  const multiPv = line.match(/\bmultipv (\d+)/)?.[1];
  const score = line.match(/\bscore (cp|mate) (-?\d+)/);
  const pv = line.match(/\bpv (.+)$/)?.[1];

  if (!depth || !score) return null;

  return {
    depth: Number(depth),
    multiPv: Number(multiPv ?? 1),
    score: {
      kind: score[1] === "cp" ? "centipawn" : "mate",
      value: Number(score[2]),
    },
    principalVariation: pv ? pv.split(/\s+/) : [],
  };
}

export function parseBestMoveLine(line) {
  return line.match(/^bestmove (\S+)/)?.[1] ?? null;
}
