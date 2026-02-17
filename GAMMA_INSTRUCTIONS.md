# Use QA slides in Gamma app (10-slide detailed PPT)

You can either **publish automatically** (script creates the deck on Gamma and gives you the URL) or **paste the outline** into Gamma manually.

---

## Option A: Publish to Gamma and get the PPT URL (recommended)

1. Get a **Gamma API key**: go to [gamma.app](https://gamma.app) → sign in → **Account / Settings** → **Developer** or **API** → create/copy API key (starts with `sk-gamma-`).

2. Add to your **`.env`**:
   ```env
   GAMMA_API_KEY=sk-gamma-your-key-here
   ```

3. Run with **`--slides --gamma-publish`** (requires `OPENAI_API_KEY` for the outline and `GAMMA_API_KEY` for publish):
   ```bash
   .venv/bin/python fetch_challenges.py --issues CEPI-27 --output report.md --slides --gamma-publish
   ```

4. The script will:
   - Generate the 10-slide outline
   - Create the presentation on Gamma
   - Print the **Gamma PPT URL** (shareable link), e.g. `https://gamma.app/docs/xxxxx`

Use that URL to open, edit, or share the 10-slide deck.

---

## Option B: Paste the outline into Gamma manually

1. Run with `--slides` only (no Gamma API key needed for this step):
   ```bash
   .venv/bin/python fetch_challenges.py --issues CEPI-27 --output report.md --slides
   ```

2. Open **report_slides_gamma.md** in your project and copy all content.

3. Go to [gamma.app](https://gamma.app) → **Create new** → **Presentation** (or **From outline**). Paste the outline. Gamma uses `---` to split slides. Generate/expand to build the deck.

---

## File locations

| File | Purpose |
|------|--------|
| `report_slides_gamma.md` | 10-slide outline (used by --gamma-publish or for manual paste) |
| `report_slides.md` | Short 2-slide summary |
