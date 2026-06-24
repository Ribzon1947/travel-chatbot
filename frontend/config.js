// Local dev: frontend-server.js runs on port 3000, backend on 8000
// Render/production: frontend is served by the backend itself — use relative URLs
window.BACKEND = window.location.port === '3000' ? 'http://localhost:8000' : '';
