import express from 'express';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dir = dirname(fileURLToPath(import.meta.url));
const app   = express();
const PORT  = 3000;

// Serve all static files from the frontend folder
app.use(express.static(join(__dir, 'frontend')));

// Named HTML routes (without .html extension)
app.get('/admin', (_, res) => res.sendFile(join(__dir, 'frontend', 'admin.html')));
app.get('/',      (_, res) => res.sendFile(join(__dir, 'frontend', 'index.html')));

app.listen(PORT, () => {
  console.log(`\n  Frontend running at  →  http://localhost:${PORT}`);
  console.log(`  Admin panel          →  http://localhost:${PORT}/admin\n`);
});
