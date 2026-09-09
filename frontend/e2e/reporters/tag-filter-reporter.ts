import * as fs from "node:fs";
import * as path from "node:path";
import type { FullConfig, Reporter, Suite } from "@playwright/test/reporter";
import { FEATURE, MODE, ROLE } from "../helpers/tags";

/**
 * Injects a click-to-select tag filter panel into the Playwright HTML report.
 *
 * The built-in report only filters via a free-text search box. This reporter
 * appends a small self-contained script to `index.html` (after the html
 * reporter has written it) that renders a "篩選" panel listing every tag seen
 * in the run, grouped 模式 / 角色 / 功能 / 其他. Toggling a tag rewrites the URL
 * hash (`#?q=@學生 @上傳文件`), which the report already treats as its search
 * query, so no report internals are touched.
 *
 * Must be listed AFTER the `html` reporter in playwright.config.ts.
 */
const PANEL_MARKER = "<!-- e2e-tag-filter-panel -->";

interface TagGroup {
  label: string;
  tags: string[];
}

export default class TagFilterReporter implements Reporter {
  private readonly seenTags = new Set<string>();
  private reportDir = "";

  onBegin(config: FullConfig, suite: Suite): void {
    this.reportDir = resolveHtmlReportDir(config);
    for (const test of suite.allTests()) {
      for (const tag of test.tags) this.seenTags.add(tag);
    }
  }

  async onEnd(): Promise<void> {
    const indexPath = path.join(this.reportDir, "index.html");
    if (!fs.existsSync(indexPath)) {
      process.stderr.write(
        `[tag-filter-reporter] ${indexPath} not found — is the html reporter listed before this one?\n`
      );
      return;
    }
    const html = fs.readFileSync(indexPath, "utf8");
    if (html.includes(PANEL_MARKER)) return;
    const groups = groupTags([...this.seenTags]);
    const injected = html.replace(
      "</body>",
      `${PANEL_MARKER}${buildPanelScript(groups)}</body>`
    );
    if (injected === html) {
      process.stderr.write(
        "[tag-filter-reporter] no </body> found in index.html; panel not injected\n"
      );
      return;
    }
    fs.writeFileSync(indexPath, injected, "utf8");
  }
}

function resolveHtmlReportDir(config: FullConfig): string {
  const fromEnv =
    process.env.PLAYWRIGHT_HTML_OUTPUT_DIR ??
    process.env.PLAYWRIGHT_HTML_REPORT;
  if (fromEnv) return path.resolve(fromEnv);
  const htmlEntry = config.reporter.find(([name]) => name === "html");
  const configured = (htmlEntry?.[1] as { outputFolder?: string } | undefined)
    ?.outputFolder;
  const configDir = config.configFile
    ? path.dirname(config.configFile)
    : process.cwd();
  return path.resolve(configDir, configured ?? "playwright-report");
}

function groupTags(tags: string[]): TagGroup[] {
  const known = (values: Record<string, string>) =>
    Object.values(values).filter(t => tags.includes(t));
  const knownAll = new Set<string>([
    ...Object.values(MODE),
    ...Object.values(ROLE),
    ...Object.values(FEATURE),
  ]);
  const other = tags.filter(t => !knownAll.has(t)).sort();
  return [
    { label: "模式", tags: known(MODE) },
    { label: "角色", tags: known(ROLE) },
    { label: "功能", tags: known(FEATURE) },
    { label: "其他", tags: other },
  ].filter(g => g.tags.length > 0);
}

function buildPanelScript(groups: TagGroup[]): string {
  const data = JSON.stringify(groups);
  return `<script>(function(){
var GROUPS=${data};
var css='#e2eTagPanel{position:fixed;right:12px;top:110px;z-index:9999;width:180px;max-height:calc(100vh - 130px);overflow:auto;background:var(--color-canvas-default,#fff);color:var(--color-fg-default,#24292f);border:1px solid var(--color-border-default,#d0d7de);border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.12);font:13px system-ui,sans-serif}'
+'#e2eTagPanel header{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--color-border-default,#d0d7de);font-weight:600;cursor:pointer}'
+'#e2eTagPanel .grp{padding:8px 12px;border-bottom:1px solid var(--color-border-muted,#eee)}#e2eTagPanel .grp:last-child{border-bottom:0}'
+'#e2eTagPanel .lbl{font-size:11px;opacity:.65;margin-bottom:6px}'
+'#e2eTagPanel button.tag{margin:0 6px 6px 0;padding:2px 9px;border-radius:999px;border:1px solid var(--color-border-default,#d0d7de);background:transparent;color:inherit;cursor:pointer;font-size:12px}'
+'#e2eTagPanel button.tag.on{background:#0969da;border-color:#0969da;color:#fff}'
+'#e2eTagPanel .clr{font-weight:400;font-size:12px;color:#0969da;cursor:pointer}'
+'#e2eTagPanel.min .body{display:none}';
var st=document.createElement('style');st.textContent=css;document.head.appendChild(st);
function query(){var h=location.hash.replace(/^#\\??/,'');var m=/(?:^|&)q=([^&]*)/.exec(h);return m?decodeURIComponent(m[1].replace(/\\+/g,' ')):'';}
function tokens(){return query().split(/\\s+/).filter(Boolean);}
function setTokens(t){var h=location.hash.replace(/^#\\??/,'').split('&').filter(function(p){return p&&!/^q=/.test(p);});if(t.length)h.push('q='+encodeURIComponent(t.join(' ')));location.hash='#?'+h.join('&');}
var panel=document.createElement('aside');panel.id='e2eTagPanel';
var hdr=document.createElement('header');var ttl=document.createElement('span');ttl.textContent='篩選標籤';var clr=document.createElement('span');clr.className='clr';clr.textContent='清除';hdr.appendChild(ttl);hdr.appendChild(clr);panel.appendChild(hdr);
var body=document.createElement('div');body.className='body';panel.appendChild(body);
GROUPS.forEach(function(g){var d=document.createElement('div');d.className='grp';var l=document.createElement('div');l.className='lbl';l.textContent=g.label;d.appendChild(l);g.tags.forEach(function(tag){var b=document.createElement('button');b.type='button';b.className='tag';b.dataset.tag=tag;b.textContent=tag.replace(/^@/,'');b.onclick=function(){var t=tokens();var i=t.indexOf(tag);if(i>=0)t.splice(i,1);else t.push(tag);setTokens(t);};d.appendChild(b);});body.appendChild(d);});
ttl.onclick=function(){panel.classList.toggle('min');};
clr.onclick=function(e){e.stopPropagation();setTokens(tokens().filter(function(t){return t.charAt(0)!=='@';}));};
function sync(){var t=tokens();panel.querySelectorAll('button.tag').forEach(function(b){b.classList.toggle('on',t.indexOf(b.dataset.tag)>=0);});}
window.addEventListener('hashchange',sync);document.body.appendChild(panel);sync();
})();</script>`;
}
