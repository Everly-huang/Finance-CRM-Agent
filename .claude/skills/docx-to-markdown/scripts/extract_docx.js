#!/usr/bin/env node
/**
 * docx 结构提取脚本 —— docx-to-markdown 技能配套工具
 *
 * 用途：将 .docx 解压目录中的 WordprocessingML 解析为可读的结构清单
 * （段落 / 表格 / 列表 / 标题 / 图片），供后续按规范手工转换为标准 Markdown。
 *
 * 用法：node extract_docx.js <word目录> [输出文件路径]
 *   示例：node extract_docx.js "C:/Temp/docx_extract/word" "C:/Temp/docx_extract/dump.txt"
 *   说明：<word目录> 必须包含 document.xml（即 docx 解压后的 word/ 目录）；
 *        输出文件省略时默认写到 <word目录>/../dump.txt
 *
 * 注意：Windows 下 Node 不识别 Git Bash 的 /tmp 路径，需先 cygpath -w 转换。
 */
'use strict';

const fs = require('fs');
const path = require('path');

// ---------- 参数与文件读取 ----------
const wordDir = process.argv[2];
if (!wordDir || !fs.existsSync(path.join(wordDir, 'document.xml'))) {
  console.error('用法: node extract_docx.js <word目录> [输出文件路径]');
  console.error('  <word目录> 必须包含 document.xml（docx 解压后的 word/ 目录）');
  process.exit(1);
}
const outPath = process.argv[3] || path.join(wordDir, '..', 'dump.txt');

const xml = fs.readFileSync(path.join(wordDir, 'document.xml'), 'utf8');
const relsPath = path.join(wordDir, '_rels', 'document.xml.rels');
const numPath = path.join(wordDir, 'numbering.xml');
const rels = fs.existsSync(relsPath) ? fs.readFileSync(relsPath, 'utf8') : '';

// ---------- 1. 图片关系映射（rId -> media 路径） ----------
const relMap = {};
for (const m of rels.matchAll(/<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"[^>]*\/>/g)) {
  relMap[m[1]] = m[2];
}
const mediaDir = path.join(wordDir, 'media');
let mediaFiles = [];
try { mediaFiles = fs.existsSync(mediaDir) ? fs.readdirSync(mediaDir) : []; } catch (e) {}

// ---------- 2. 编号格式映射：numId -> decimal / bullet ----------
// 链路：w:num(numId) -> w:abstractNumId -> w:abstractNum -> w:lvl[ilvl=0] -> w:numFmt
const numFmtMap = {};
if (fs.existsSync(numPath)) {
  const nx = fs.readFileSync(numPath, 'utf8');
  const numMap = {};
  for (const m of nx.matchAll(/<w:num w:numId="(\d+)"[^>]*>\s*<w:abstractNumId w:val="(\d+)"/g)) {
    numMap[m[1]] = m[2];
  }
  for (const m of nx.matchAll(/<w:abstractNum w:abstractNumId="(\d+)"[\s\S]*?<\/w:abstractNum>/g)) {
    const lvl0 = m[0].match(/<w:lvl w:ilvl="0"[\s\S]*?<\/w:lvl>/);
    let fmt = '?';
    if (lvl0) {
      const f = lvl0[0].match(/<w:numFmt w:val="(\w+)"/);
      fmt = f ? f[1] : '?';
    }
    for (const [numId, aid] of Object.entries(numMap)) {
      if (aid === m[1]) numFmtMap[numId] = fmt;
    }
  }
}

// ---------- 3. 拆分为块级元素（段落 / 表格） ----------
const body = xml.match(/<w:body>([\s\S]*)<\/w:body>/)[1];
const blocks = [];
const re = /<w:p\b[\s\S]*?<\/w:p>|<w:tbl\b[\s\S]*?<\/w:tbl>/g;
let m;
while ((m = re.exec(body)) !== null) {
  blocks.push({ type: m[0].startsWith('<w:tbl') ? 'table' : 'para', xml: m[0] });
}

// ---------- 4. 段落 run 级文本与格式提取 ----------
// 返回 [{text, bold, italic, sz, brCount, tabCount}]；sz 为磅值（w:sz 半磅值/2）
function paraRuns(pXml) {
  const runs = [];
  const runRe = /<w:r\b[\s\S]*?<\/w:r>|<w:hyperlink\b[\s\S]*?<\/w:hyperlink>/g;
  let rm;
  while ((rm = runRe.exec(pXml)) !== null) {
    const rXml = rm[0];
    const bold = /<w:b\/>/.test(rXml) || /<w:b\s/.test(rXml);
    const italic = /<w:i\/>/.test(rXml) || /<w:i\s/.test(rXml);
    const szMatch = rXml.match(/<w:sz w:val="(\d+)"/);
    const sz = szMatch ? parseInt(szMatch[1]) / 2 : null;
    let text = '';
    const tRe = /<w:t(?: [^>]*)?>([\s\S]*?)<\/w:t>/g;
    let tm;
    while ((tm = tRe.exec(rXml)) !== null) {
      text += tm[1]
        .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"').replace(/&apos;/g, "'");
    }
    const brCount = (rXml.match(/<w:br\/>/g) || []).length;
    const tabCount = (rXml.match(/<w:tab\/>/g) || []).length;
    if (text || brCount || tabCount) {
      runs.push({ text, bold, italic, sz, brCount, tabCount });
    }
  }
  return runs;
}

// ---------- 5. 单块转清单行 ----------
function dumpBlock(b, i) {
  if (b.type === 'para') {
    const p = b.xml;
    const numPr = p.match(/<w:numPr>[\s\S]*?<\/w:numPr>/);
    let ilvl = null, numId = null;
    if (numPr) {
      const il = numPr[0].match(/<w:ilvl w:val="(\d+)"/);
      const ni = numPr[0].match(/<w:numId w:val="(\d+)"/);
      ilvl = il ? parseInt(il[1]) : null;
      numId = ni ? parseInt(ni[1]) : null;
    }
    const outlineMatch = p.match(/<w:outlineLvl w:val="(\d+)"/);
    const outline = outlineMatch ? parseInt(outlineMatch[1]) : null;
    const runs = paraRuns(p);
    const hasImg = /<w:drawing|<w:pict/.test(p);
    const maxSz = runs.reduce((a, r) => Math.max(a, r.sz || 0), 0);
    const allBold = runs.length > 0 && runs.every(r => r.bold || !r.text.trim());
    const fullText = runs.map(r => r.text).join('');
    if (!fullText.replace(/\s+/g, ' ').trim() && !hasImg) return null; // 跳过空段
    const fmt = numId != null ? (numId === 0 ? 'none' : (numFmtMap[numId] || '?')) : null;
    const lines = [`--- BLOCK ${i} [P] sz=${maxSz} bold=${allBold} numId=${numId} ilvl=${ilvl} outline=${outline} fmt=${fmt} img=${hasImg}`];
    for (const r of runs) {
      const tags = [];
      if (r.bold) tags.push('B');
      if (r.italic) tags.push('I');
      if (r.brCount) tags.push(`br×${r.brCount}`);
      if (r.tabCount) tags.push(`tab×${r.tabCount}`);
      lines.push(`  [${tags.join('')}]${r.text ? ' ' + JSON.stringify(r.text) : ''}`);
    }
    if (hasImg) {
      const emb = b.xml.match(/r:embed="([^"]+)"/g) || [];
      lines.push(`  IMG refs: ${emb.map(e => { const id = e.match(/r:embed="([^"]+)"/)[1]; return relMap[id] || '?'; }).join(', ')}`);
    }
    return lines.join('\n');
  } else {
    // 表格：逐行逐格取文本；span 为横向跨列数，vmerge 为纵向合并
    const rows = [];
    const trRe = /<w:tr\b[\s\S]*?<\/w:tr>/g;
    let trm;
    while ((trm = trRe.exec(b.xml)) !== null) {
      const cells = [];
      const tcRe = /<w:tc\b[\s\S]*?<\/w:tc>/g;
      let tcm;
      while ((tcm = tcRe.exec(trm[0])) !== null) {
        const span = tcm[0].match(/<w:gridSpan w:val="(\d+)"/);
        const vmerge = /<w:vMerge/.test(tcm[0]);
        const cellText = [];
        const pRe = /<w:p\b[\s\S]*?<\/w:p>/g;
        let pm;
        while ((pm = pRe.exec(tcm[0])) !== null) {
          const runs = paraRuns(pm[0]);
          cellText.push(runs.map(r => r.text + '<br>'.repeat(r.brCount)).join(''));
        }
        cells.push({ text: cellText.join('\n'), span: span ? parseInt(span[1]) : 1, vmerge });
      }
      rows.push(cells);
    }
    const lines = [`--- BLOCK ${i} [TABLE] rows=${rows.length} cols=${rows[0] ? rows[0].length : 0}`];
    rows.forEach((row, ri) => {
      lines.push(`  ROW ${ri}: ` + JSON.stringify(row.map(c => c.text.replace(/\s+/g, ' ').trim())));
      if (row.some(c => c.span > 1 || c.vmerge)) lines.push(`  spans: ` + row.map(c => c.vmerge ? 'vm' : c.span).join(','));
    });
    return lines.join('\n');
  }
}

// ---------- 6. 汇总输出 ----------
const out = [];
out.push(`# docx 结构清单`);
out.push(`# 图片: ${mediaFiles.length ? mediaFiles.join(', ') : '(无)'}`);
out.push(`# 编号格式(numId->fmt): ${Object.entries(numFmtMap).map(([k, v]) => `${k}=${v}`).join(' ') || '(无编号)'}`);
out.push('');
blocks.forEach((b, i) => {
  const d = dumpBlock(b, i);
  if (d) out.push(d);
});
fs.writeFileSync(outPath, out.join('\n'), 'utf8');
console.log(`blocks: ${blocks.length}, media: ${mediaFiles.length ? mediaFiles.join(', ') : '(无)'}`);
console.log(`dump -> ${outPath}, lines: ${out.length}`);
