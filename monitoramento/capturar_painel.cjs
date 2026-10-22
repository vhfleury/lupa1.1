const { chromium } = require('/e2e/node_modules/playwright');
const fs = require('fs');
(async () => {
  const senha = fs.readFileSync('/segredo/grafana_senha', 'utf8').trim();
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 }, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' });
  await p.goto('http://localhost:3000/login');
  await p.fill('input[name="user"]', 'admin');
  await p.fill('input[name="password"]', senha);
  await p.click('button[type="submit"]');
  await p.waitForURL(/.*(?<!login)$/, { timeout: 20000 }).catch(() => {});
  await p.goto('http://localhost:3000/d/lupa-piloto/lupa-piloto?orgId=1&from=now-10m&to=now&kiosk');
  await p.waitForTimeout(8000);
  await p.screenshot({ path: '/saida/grafana.png', fullPage: true });
  await b.close();
  console.log('ok');
})().catch(e => { console.error(String(e)); process.exit(1); });
