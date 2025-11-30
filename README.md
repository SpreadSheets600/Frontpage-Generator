# Frontpage Generator

A web application for generating academic frontpage covers automatically. Built with Flask, featuring a modern UI and an admin dashboard for managing subjects and streams.

## Features

- Generate frontpage covers with user input (name, roll, registration, subject, stream, semester)
- Admin dashboard for managing subjects, streams, and viewing logs
- Responsive design optimized for mobile and desktop
- Live counter showing total documents generated
- JSON-based configuration for easy management

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

## Project Structure

- `main.py`: Flask application and API routes
- `templates/`: HTML templates (layout, index, admin)
- `static/`: Static assets (template image, fonts)
- `admin_config.json`: Configuration for subjects and streams
- `frontpage_logs.jsonl`: Log of generated documents
- `requirements.txt`: Python dependencies

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Make your changes and test thoroughly.
4. Submit a pull request.
