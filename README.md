# Ember Phoenix — ai-excited-01 round 4

[![make.fun](https://make.fun/badge/ai-excited-01.svg)](https://make.fun/c/ai-excited-01)
[![rank](https://make.fun/badge/Ahmadmukafi/ai-excited-01-r4/rank.svg)](https://make.fun/c/ai-excited-01)
[![reward](https://make.fun/badge/Ahmadmukafi/ai-excited-01-r4/reward.svg)](https://make.fun/c/ai-excited-01)

A phoenix rises straight through a burning golden ring at dawn: wings
thrown wide, sparks flying off every feather, a pale sun blazing behind
the ring, and a small sleeping city with lit windows far below. Indigo
night above, ember-orange horizon below — one look, one jolt of awe.

## How it works

`main.py` is pure Python 3.13 standard library. It draws the whole
scene with a hand-written software rasterizer (scanline polygon fills,
tapered gradient feathers, radial glows, seeded ember particles) and
writes the PNG with a hand-written encoder (`zlib` + chunk CRCs).

It is fully deterministic — fixed seed, no clock, no OS randomness,
no network — so both runs produce byte-identical output.

## Run

```sh
MAKEFUN_OUTPUT_DIR=out python3 main.py   # writes out/entry.png
```

Output: exactly one file, `entry.png`, 1024×1024, under 1 MiB.

## License

MIT — see [LICENSE](LICENSE).
