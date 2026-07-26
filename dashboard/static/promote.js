/* Promote quarantine tool via local dashboard API */
async function promoteTool(filename) {
  if (!filename) return;
  if (!confirm('Promote ' + filename + ' to persistent tools?')) return;
  try {
    const r = await fetch('/api/promote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: filename }),
    });
    const data = await r.json();
    if (!r.ok) {
      alert('Promote failed: ' + (data.detail || JSON.stringify(data)));
      return;
    }
    alert('Promoted: ' + (data.to || filename));
  } catch (e) {
    alert('Promote error: ' + e);
  }
}
