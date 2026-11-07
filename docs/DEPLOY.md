# Deploying the Diabetes Risk Screening Tool

## 1. Put the code on GitHub

From the repo root, with the [GitHub CLI](https://cli.github.com/) signed in (`gh auth login`):

```bash
gh repo create diabetes-risk-screening --public --source . --remote origin --push
```

Without the CLI: create an empty public repo named `diabetes-risk-screening` on github.com (no README, no license), then:

```bash
git remote add origin https://github.com/<your-username>/diabetes-risk-screening.git
git push -u origin main
```

The `models/` folder (the `.joblib` files and `meta.json`) must be committed: the app loads them at startup.

One-time setup on each clone, so the commit-message hook runs:

```bash
git config core.hooksPath .githooks
```

## 2. Deploy on Streamlit Community Cloud

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. Click **Create app** / **New app** → **Deploy a public app from GitHub**.
3. Repository: `<your-username>/diabetes-risk-screening`, branch: `main`, main file path: `app.py`.
4. Open **Advanced settings** → Python version **3.12**.
5. Click **Deploy**. The first build takes a few minutes while `requirements.txt` installs.
6. Copy the app URL (`https://<something>.streamlit.app`) into the README.

Every push to `main` redeploys the app automatically.

## 3. Pre-publish self-check

- [ ] Open the live URL in a **private/incognito window** (not signed in) and it loads.
- [ ] Try **bad input** (e.g. height 0, weight 500): the app shows a clear error instead of crashing.
- [ ] README has the **live app link**, a **screenshot**, and the **results table**.
- [ ] `notebook.ipynb` runs **top to bottom** on a fresh kernel (Kernel → Restart & Run All).
- [ ] **Every number** in the README and app comes from your own results in the notebook.
- [ ] Dataset credited: CDC Diabetes Health Indicators, UCI Machine Learning Repository, <https://archive.ics.uci.edu/dataset/891>.
- [ ] CI is green on the GitHub **Actions** tab.

## 4. Before a demo

Community Cloud apps **sleep when idle**. Open the URL a few minutes before a demo and click **"Yes, get this app back up"** if it shows the sleep page, so it is awake when you present.
