# Clipboard

Cogitus supports two clipboard strategies:

- OSC 52 (primary)
- `pyperclip` fallback

## Terminal Compatibility

OSC 52 works in many modern terminals (for example Ghostty, Kitty, WezTerm,
iTerm2, Windows Terminal).

For terminals without OSC 52 pass-through, fallback clipboard tools may be
required (`xclip`, `xsel`, `pbcopy`).

## tmux

Enable clipboard pass-through:

```tmux
set -g set-clipboard on
```

## Context-Sensitive `y` Copy

- In editor contexts, `y` copies the current selection.
- In rendered Markdown view, `y` copies selected text when detectable.
- If rendered-view selection is not detectable in your terminal/context,
  Cogitus falls back to copying the full idea body.
