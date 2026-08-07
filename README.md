# Collectables Earner

This repository contains a self-contained fitness incentive tracker that uses GitHub Actions, GitHub Pages, and Telegram to run a free automation loop.

## Files
- app.py: the Python entry point for storing activity and weight data, generating the dashboard, and exposing a lightweight webhook endpoint.
- index.html: the dashboard template for GitHub Pages.
- .github/workflows/tracker.yml: workflow to rebuild and deploy the dashboard whenever the repository changes or a repository dispatch event arrives.
- tests/test_app.py: regression tests for weight-gate and activity-earning logic.

## Local usage
1. Run `python3 app.py render` to rebuild the dashboard.
2. Run `python3 app.py webhook` and send JSON payloads such as `{"kind": "weight", "date": "2026-08-03", "weight": 204.0}`.
3. Run `python3 app.py daily-prompt` to emit the scheduled workout prompt text (this will send an SMS if Twilio env vars are configured).

## GitHub Actions deployment
1. Push this repository to GitHub.
2. In repository Settings → Secrets and variables → Actions, add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `SITE_URL` (your GitHub Pages URL)
3. Enable GitHub Pages with the GitHub Actions deployment source.
4. Trigger `.github/workflows/tracker.yml` on `main` (manual trigger, push, schedule, or repository dispatch).
5. The workflow runs `python app.py render`, stages only the generated `index.html` (and optional `CNAME`) into a `site/` artifact directory, and deploys that artifact with `actions/deploy-pages`.

## Webhook idea
You can call the tracked webhook URL from a Shortcut, Apple Health export, or a simple GitHub repository dispatch action with a JSON body.
