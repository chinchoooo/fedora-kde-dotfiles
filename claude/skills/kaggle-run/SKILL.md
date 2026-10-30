---
name: kaggle-run
description: Run a notebook or script on Kaggle (CPU/GPU) and fetch its output with the Kaggle CLI wrapper. Use when the user wants something run on Kaggle.
---

1. Credentials: the user logs in themselves (`kaggle auth login` or a token in `~/.kaggle/access_token`, chmod 600). Never read, print or commit them. If `kaggle kernels list --mine` fails with an auth error, ask the user to log in; do not ask for passwords.
2. Make a folder under `~/code/kaggle-runs/<name>/` with the script/notebook and `kernel-metadata.json` (`kaggle kernels init -p <folder>` creates a template; set `id`, `title`, `code_file`, `language`, `kernel_type`, `enable_gpu`, `enable_internet`).
3. Run `~/code/kaggle-runs/kaggle_run.sh <folder> [--accelerator NvidiaTeslaT4] [-t seconds]` in the background; it pushes, polls status every 30 s, and downloads output to `<folder>/output`.
4. Report the status line strings you actually saw (the exact words have not been verified against a live run yet) and the output files. GPU quota is limited and needs phone verification on the account.
5. For steps that need the website UI only, use Claude in Chrome (Chrome only, not Helium) as a fallback.
