# Recording the README demo GIF

The hero GIF is the single highest-leverage adoption asset. It should show, in
~10 seconds:

1. A prompt typed in Claude Code (or any host).
2. The live route banner: `🎯 chuzom → <model> · <task>/<complexity> · saved $X`.
3. `chuzom summary --watch` updating with the tier distribution + savings.

## Capture (asciinema → GIF, crisp + small)

```bash
# 1. Install the tools
brew install asciinema agg          # agg = asciinema gif generator

# 2. Record a focused ~10s session
asciinema rec demo.cast \
  --cols 100 --rows 28 --idle-time-limit 1.5

#    In the recording, run a couple of real prompts through a host so the
#    banner fires, then:
#      chuzom summary --watch
#    Let it tick once or twice, then Ctrl-C and `exit`.

# 3. Render to GIF (theme + speed tuned for a hero banner)
agg demo.cast docs/assets/demo.gif \
  --theme monokai --font-size 16 --speed 1.3 --cols 100 --rows 28

# 4. Keep it small (<2 MB renders fast on GitHub/PyPI)
#    If too large, trim the cast or drop --rows.
```

## Wire it into the README

Replace the `DEMO GIF SLOT` HTML comment near the top of `README.md` with:

```html
<p align="center">
  <img src="https://raw.githubusercontent.com/ypollak2/chuzom/main/docs/assets/demo.gif"
       alt="chuzom routing a prompt and showing live savings" width="760">
</p>
```

(Served via `raw.githubusercontent.com` so it renders on GitHub. Note: animated
GIFs do **not** render on PyPI — that's fine, the GitHub README is the surface
that drives stars.)

## Tips

- Pre-warm: have a couple of cached/free routes ready so the banner shows a
  real saved-$ number, not `$0.00`.
- Use `chuzom share --svg` to generate a static savings card for social posts
  where a GIF won't autoplay.
