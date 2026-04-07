# Frontpage Generator

A web application for generating academic frontpage covers automatically. The project is D1-first: catalog, streams, and logs are served from Cloudflare D1 through the Python Worker API.

## Features

- Generate frontpage covers with user input (name, roll, registration, subject, stream, semester)
- Admin dashboard for managing subjects, streams, and viewing logs (all persisted in D1)
- Responsive design optimized for mobile and desktop
- Live counter showing total documents generated
- Cloudflare D1-backed catalog and logging APIs

## Installation

1. Clone the repository:

   ```
   git clone https://github.com/SpreadSheets600/Frontpage-Generator.git
   cd Frontpage-Generator
   ```

2. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   Create a `.env` file with:

   ```
   ADMIN_API_KEY=your_secure_api_key_here
   PORT=5000
   ```

4. Run the application:

   ```
   python main.py
   ```

   Visit `http://localhost:5000` in your browser.

## Usage

### Generating Frontpages

1. Fill out the form with your details (name, roll number, registration, semester, stream, subject).
2. Click "Generate Document" to download the frontpage cover as a PNG.

### Admin Dashboard

1. Navigate to `/admin/dashboard`.
2. Enter the admin API key.
3. Manage subjects: Add, edit, or delete subjects across categories (CS, ECE, AIML).
4. Manage streams: Add or remove stream labels.
5. View logs: See recent generation events.

## API Endpoints

- `GET /`: Redirects to the generator page
- `GET /frontpages`: Displays the generator form
- `POST /frontpages`: Generates and downloads the frontpage
- `GET /admin/dashboard`: Admin dashboard page
- `GET /admin/subjects`: Get subjects data (requires auth)
- `POST /admin/subjects`: Add a new subject (requires auth)
- `PUT /admin/subjects`: Edit an existing subject (requires auth)
- `DELETE /admin/subjects`: Delete a subject (requires auth)
- `GET /admin/streams`: Get streams data (requires auth)
- `POST /admin/streams`: Add a stream (requires auth)
- `DELETE /admin/streams`: Delete a stream (requires auth)
- `GET /admin/logs`: Get recent logs (requires auth)
- `GET /api/stats`: Get total generated documents count

## Deployment

This app is configured for deployment on Render:

1. Push your code to GitHub.
2. Create a new Web Service on Render.
3. Connect your GitHub repo.
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `python main.py`
6. Add environment variables in Render's dashboard.

## Cloudflare Split Deployment

This repository now also includes a Cloudflare-oriented path:

- static frontend at [index.html](/home/spreadsheets600/Development/Frontpage-Generator/index.html) for Cloudflare Pages
- separate Python Worker API under [cloudflare-api/src/worker.py](/home/spreadsheets600/Development/Frontpage-Generator/cloudflare-api/src/worker.py)
- D1 schema at [cloudflare-api/schema.sql](/home/spreadsheets600/Development/Frontpage-Generator/cloudflare-api/schema.sql)

### Public endpoints in the Worker

- `GET /api/health`
- `GET /api/stats`
- `GET /api/catalog`
- `POST /api/generate-pdf`
- `POST /api/log-generation`

### What the Worker does

- reads catalog and stats from D1
- provides admin endpoints for subjects, streams, and logs backed by D1
- accepts normal-user form input as JSON
- logs successful client-side generations into D1
- still exposes the Browser Rendering-backed `/api/generate-pdf` route for compatibility, but the Pages frontend now renders the PDF or PNG locally from `static/template.png` to avoid Browser Rendering rate limits

### Setup steps

1. Create a D1 database and update `database_id` in [cloudflare-api/wrangler.toml](/home/spreadsheets600/Development/Frontpage-Generator/cloudflare-api/wrangler.toml).
2. Apply [cloudflare-api/schema.sql](/home/spreadsheets600/Development/Frontpage-Generator/cloudflare-api/schema.sql) to D1.
3. Set `ALLOWED_ORIGIN`, `PUBLIC_TEMPLATE_URL`, and optionally `PUBLIC_FONT_URL` in [cloudflare-api/wrangler.toml](/home/spreadsheets600/Development/Frontpage-Generator/cloudflare-api/wrangler.toml).
4. Add Worker secrets for `CLOUDFLARE_ACCOUNT_ID` and `BROWSER_RENDERING_API_TOKEN`.
5. Open [index.html](/home/spreadsheets600/Development/Frontpage-Generator/index.html) with `?apiBase=https://your-worker.your-subdomain.workers.dev` once after deploy, or replace the `DEPLOYED_API_BASE` constant with your Worker URL.
6. Deploy the Worker and then deploy the static site to Pages.

### Notes

- The Pages site and the Worker are intentionally separate origins, so the Worker sends CORS headers.
- PDF generation depends on Cloudflare Browser Rendering and a public URL for `static/template.png`.
- The original Flask app is still present if you want to keep your current local workflow.
- The Worker supports a local HTML preview mode only when `LOCAL_RENDER_MODE=html` is explicitly set in local development. Do not enable that in production.

### Local test before deploy

Use this flow if you want to verify the Worker from your machine before pushing to Cloudflare:

1. Copy [cloudflare-api/.dev.vars.example](/home/spreadsheets600/Development/Frontpage-Generator/cloudflare-api/.dev.vars.example) to `cloudflare-api/.dev.vars` and fill in your Cloudflare account ID and Browser Rendering token.
2. In [cloudflare-api/wrangler.toml](/home/spreadsheets600/Development/Frontpage-Generator/cloudflare-api/wrangler.toml), temporarily set `ALLOWED_ORIGIN` to `http://127.0.0.1:3000`. If you want HTML preview mode instead of real PDF generation, also set `LOCAL_RENDER_MODE = "html"` and point `PUBLIC_TEMPLATE_URL` and `PUBLIC_FONT_URL` at your local static server.
3. Initialize a local D1 database from schema + seed SQL:

   ```
   npm run cf:d1:init
   ```

4. Start the Worker locally:

   ```
   npm run cf:dev
   ```

5. In another terminal, serve the static frontend:

   ```
   npm run frontend:dev
   ```

6. Open `http://127.0.0.1:3000/index.html`. The frontend now auto-targets `http://127.0.0.1:8787` on localhost.

If you need a different Worker URL during testing, open the page with `?apiBase=http://127.0.0.1:8787` or another base URL. The frontend stores that override in `localStorage`.

Quick API smoke tests:

```
curl http://127.0.0.1:8787/api/health
curl http://127.0.0.1:8787/api/catalog
curl -X POST http://127.0.0.1:8787/api/generate-pdf \
  -H 'Content-Type: application/json' \
  --output test.pdf \
  --data '{
    "name":"Test Student",
    "roll":"123",
    "reg":"456",
    "stream_label":"CSE",
    "semester_label":"1st",
    "subject_name":"Mathematics I",
    "subject_code":"MATH101"
  }'
```

The D1 seed is loaded from `cloudflare-api/seed.generated.sql`. If you want to regenerate that file, use `cloudflare-api/generate_seed_sql.py` manually.

Without `LOCAL_RENDER_MODE = "html"`, the legacy PDF route uses Cloudflare Browser Rendering and requires valid Cloudflare credentials plus a publicly reachable template asset URL. The current Pages frontend does not depend on that route for normal downloads.

### Cloudflare deploy checklist

1. Create a D1 database:

   ```
   npx wrangler d1 create frontpage-db
   ```

2. Put the returned database ID into [cloudflare-api/wrangler.toml](/home/spreadsheets600/Development/Frontpage-Generator/cloudflare-api/wrangler.toml).

3. Apply schema and seed data to the remote D1 database:

   ```
   cd cloudflare-api
   npx wrangler d1 execute frontpage-db --remote --file=./schema.sql
   npx wrangler d1 execute frontpage-db --remote --file=./seed.generated.sql
   ```

4. Set Worker secrets:

   ```
   cd cloudflare-api
   npx wrangler secret put CLOUDFLARE_ACCOUNT_ID
   npx wrangler secret put BROWSER_RENDERING_API_TOKEN
   ```

5. Update [cloudflare-api/wrangler.toml](/home/spreadsheets600/Development/Frontpage-Generator/cloudflare-api/wrangler.toml) so:
   `ALLOWED_ORIGIN` matches your Pages URL and the public asset URLs point at your Pages-hosted `static/` files.

6. Deploy the Worker:

   ```
   cd cloudflare-api
   npx wrangler deploy
   ```

7. Deploy the static frontend to Cloudflare Pages, then open the site with:
   `?apiBase=https://your-worker.your-subdomain.workers.dev`

## Project Structure

This repository currently ships two runnable paths that share the same Cloudflare D1-backed catalog:

- `index.html`: standalone static generator page for Cloudflare Pages. It renders PNG/PDF locally in the browser from `static/template.png` and logs usage through the Worker API.
- `static/`: assets used by the static frontend and the Flask app, including `template.png`, `Sans.ttf`, and the downloadable `index_page.pdf`.
- `cloudflare-api/src/worker.py`: Cloudflare Python Worker. It serves `/api/catalog`, `/api/stats`, `/api/generate-pdf`, and `/api/log-generation`.
- `cloudflare-api/wrangler.toml`: Worker deployment config, D1 binding, and public asset origin settings for Pages.
- `cloudflare-api/schema.sql`: D1 schema for semesters, streams, subjects, and generation logs.
- `cloudflare-api/generate_seed_sql.py`: optional helper to regenerate D1 seed SQL from a local catalog file.
- `main.py`: Flask host/proxy for local/server deployment. It serves UI files and forwards API calls to the Worker, so data still comes from D1.
- `templates/`: Flask templates for the legacy app UI and admin pages.
- `admin_config.json`: optional local file used only if you manually regenerate D1 seed SQL.
- `frontpage_logs.jsonl`: legacy local log artifact; runtime logging is stored in D1.
- `requirements.txt`, `pyproject.toml`: Python dependency definitions for the Flask app and local tooling.
- `package.json`: helper scripts for local Cloudflare Worker development and local static frontend serving.

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Make your changes and test thoroughly.
4. Submit a pull request.
