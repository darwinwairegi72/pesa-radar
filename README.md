# Pesa Radar pipeline

This project collects Kenyan Treasury bill results and bond or IPO headlines, turns them into draft posts, and publishes the ones **a person approves** to a website. It runs on GitHub's free automation, so there is no server to look after.

## How it works

1. **Collect (automatic).** On a schedule, the collectors read the CBK Treasury bills page and a few headline pages. New results become draft files in `data/items/`.
2. **Check (a person, about 2 minutes).** GitHub emails you an issue called "Review needed". It links to each draft and to the original source. Compare the numbers with the source, then approve or reject.
3. **Publish (automatic).** The moment a draft is approved, the website rebuilds and updates itself.

Nothing reaches the website without step 2.

What the collectors do:
- **Treasury bill results.** Reads the numbers from CBK's results PDF and runs checks (all three bills present, rates plausible, accepted amount not bigger than bids, two places in the PDF agree). A draft that fails the checks is marked `needs_attention` and lists what looked wrong.
- **Headlines (bond sales, IPO approvals).** Saves only the headline and the link. It does not extract prices or dates, because a wrong figure in a financial post does real harm. You read the original and decide.

## One-time setup (about 30 minutes, no coding)

1. Create a free account at github.com.
2. Create a new repository named `pesa-radar` (public, so that the free website hosting works).
3. Upload everything in this folder to the repository. Include the hidden `.github` folder: it holds the automation.
4. In the repository, open **Settings > Pages** and set **Source** to **GitHub Actions**.
5. Open **Settings > Actions > General**, and under **Workflow permissions** choose **Read and write permissions**. Save.
6. Edit `config.yaml` (pencil icon on GitHub): put your real email in `user_agent`, and replace the disclaimer placeholder after a lawyer has reviewed it.
7. Open the **Actions** tab, choose **Collect new data**, then **Run workflow**. This is your first run.
8. Wait a few minutes. Open the **Issues** tab. You should see "Review needed".

## Approving a draft

1. Open the link in the issue. It opens the draft file in the GitHub editor.
2. Check the numbers against the source link in the issue.
3. Change `"status": "pending"` to `"status": "approved"` (or `"rejected"`).
4. Choose **Commit changes**. The site updates in a couple of minutes.

Be careful to keep the quotation marks and commas as they are. If a file gets a typo, the system skips it and prints a warning, rather than breaking the site.

## Things to know

- **The first run may need adjusting.** The collectors were tested against the layout of a real CBK results PDF, but not run against the live websites. If the first run reports "things that did not work", copy that text to Claude and it can be fixed quickly. The two addresses marked `VERIFY` in `config.yaml` are best guesses.
- **Check each source's terms of use** before relying on automated collection, and keep the polite pause in `config.yaml`.
- **Schedules can run a little late.** GitHub may start scheduled jobs several minutes after the set time.
- **Free GitHub Pages needs a public repository.** The code and drafts are public. That is fine for public market data, but do not store anything private here. Cloudflare Pages or Netlify can host from a private repository if you prefer.
- **Not investment advice.** Keep posts factual, with the source and date shown.

## Running it on your own computer (optional, for developers)

```
pip install -r requirements.txt
python -m pytest          # run the tests
python -m pipeline.run    # collect
python -m pipeline.publish  # build the site into site/
```
