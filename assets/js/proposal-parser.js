const MAMMOTH_URL = 'https://cdn.jsdelivr.net/npm/mammoth@1.10.0/mammoth.browser.min.js';
const PDFJS_URL = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.min.mjs';
const PDFJS_WORKER_URL = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.min.mjs';

let mammothPromise = null;
let pdfJsPromise = null;

function normalizeText(value = '') {
  return String(value)
    .replace(/\u00a0/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\s*\n\s*/g, '\n')
    .trim();
}

function wordCount(text = '') {
  const normalized = normalizeText(text);
  return normalized ? normalized.split(/\s+/).filter(Boolean).length : 0;
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      if (window.mammoth) resolve();
      else existing.addEventListener('load', resolve, { once: true });
      return;
    }

    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error('Library parser DOCX gagal dimuat.'));
    document.head.appendChild(script);
  });
}

async function getMammoth() {
  if (!mammothPromise) {
    mammothPromise = (async () => {
      await loadScript(MAMMOTH_URL);
      if (!window.mammoth) throw new Error('Parser DOCX tidak tersedia.');
      return window.mammoth;
    })();
  }
  return mammothPromise;
}

async function getPdfJs() {
  if (!pdfJsPromise) {
    pdfJsPromise = import(PDFJS_URL).then((pdfjs) => {
      pdfjs.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_URL;
      return pdfjs;
    });
  }
  return pdfJsPromise;
}

function paragraphTypeFromElement(element) {
  const tag = element.tagName.toLowerCase();
  if (/^h[1-6]$/.test(tag)) return 'heading';
  if (tag === 'li') return 'list';
  if (tag === 'blockquote') return 'quote';
  return 'body';
}

function paragraphStyleFromElement(element) {
  const tag = element.tagName.toLowerCase();
  if (/^h[1-6]$/.test(tag)) return tag.toUpperCase();
  if (element.querySelector('strong')) return 'Bold paragraph';
  return tag.toUpperCase();
}

async function parseDocx(arrayBuffer) {
  const mammoth = await getMammoth();
  const { value, messages } = await mammoth.convertToHtml(
    { arrayBuffer },
    {
      includeDefaultStyleMap: true,
      styleMap: [
        "p[style-name='Title'] => h1:fresh",
        "p[style-name='Subtitle'] => h2:fresh",
      ],
    }
  );

  const documentHtml = new DOMParser().parseFromString(value, 'text/html');
  const elements = Array.from(documentHtml.body.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,blockquote'));
  const paragraphs = [];
  const seen = new Set();

  for (const element of elements) {
    const text = normalizeText(element.textContent);
    if (!text) continue;

    const key = `${element.tagName}:${text}`;
    if (seen.has(key)) continue;
    seen.add(key);

    paragraphs.push({
      paragraph_index: paragraphs.length,
      paragraph_type: paragraphTypeFromElement(element),
      text_content: text,
      style_name: paragraphStyleFromElement(element),
      word_count: wordCount(text),
    });
  }

  return {
    paragraphs,
    warnings: (messages || []).map((message) => message.message).filter(Boolean),
  };
}

function buildPdfLines(items) {
  const lines = [];
  let current = [];

  for (const item of items) {
    const text = normalizeText(item.str || '');
    if (text) current.push(text);

    if (item.hasEOL) {
      const line = normalizeText(current.join(' '));
      if (line) lines.push(line);
      current = [];
    }
  }

  const tail = normalizeText(current.join(' '));
  if (tail) lines.push(tail);
  return lines;
}

async function parsePdf(arrayBuffer) {
  const pdfjs = await getPdfJs();
  const pdf = await pdfjs.getDocument({ data: new Uint8Array(arrayBuffer) }).promise;
  const paragraphs = [];

  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const content = await page.getTextContent();
    const lines = buildPdfLines(content.items);

    for (const line of lines) {
      paragraphs.push({
        paragraph_index: paragraphs.length,
        paragraph_type: detectSectionCode(line) ? 'heading' : 'body',
        text_content: line,
        style_name: `PDF page ${pageNumber}`,
        word_count: wordCount(line),
      });
    }
  }

  return {
    paragraphs,
    warnings: ['PDF tidak menyimpan style Word; deteksi struktur menggunakan pola teks.'],
  };
}

export function detectSectionCode(text = '') {
  const normalized = normalizeText(text).toUpperCase();

  const chapter = normalized.match(/^BAB\s+([IVXLCDM]+)\b/);
  if (chapter) return `BAB ${chapter[1]}`;

  if (/^(DAFTAR\s+PUSTAKA|REFERENSI)\b/.test(normalized)) return 'REFERENSI';
  if (/^LAMPIRAN\b/.test(normalized)) return 'LAMPIRAN';
  return null;
}

function titleFromSectionText(text, code) {
  let title = normalizeText(text);

  if (code.startsWith('BAB ')) {
    title = title.replace(/^BAB\s+[IVXLCDM]+\s*[-–—.:]?\s*/i, '');
  } else if (code === 'REFERENSI') {
    title = title.replace(/^(DAFTAR\s+PUSTAKA|REFERENSI)\s*[-–—.:]?\s*/i, '');
  } else if (code === 'LAMPIRAN') {
    title = title.replace(/^LAMPIRAN\s*[-–—.:]?\s*/i, '');
  }

  if (title) return title;

  return ({
    'BAB I': 'Pendahuluan',
    'BAB II': 'Kajian Pustaka',
    'BAB III': 'Metode Penelitian',
    'BAB IV': 'Hasil dan Pembahasan',
    'BAB V': 'Kesimpulan',
    REFERENSI: 'Daftar Pustaka',
    LAMPIRAN: 'Lampiran',
  })[code] || 'Bagian';
}

function attachSections(paragraphs) {
  const sections = [];
  const sectionMap = new Map();
  let currentSection = null;

  for (const paragraph of paragraphs) {
    const code = detectSectionCode(paragraph.text_content);

    if (code) {
      currentSection = code;
      if (!sectionMap.has(code)) {
        const section = {
          section_code: code,
          section_title: titleFromSectionText(paragraph.text_content, code),
          section_type: code === 'REFERENSI' ? 'reference' : code === 'LAMPIRAN' ? 'appendix' : 'chapter',
          sort_order: (sections.length + 1) * 10,
        };
        sectionMap.set(code, section);
        sections.push(section);
      }
    }

    paragraph.section_code = currentSection;
  }

  return sections;
}

function findLineIndex(lines, pattern) {
  return lines.findIndex((line) => pattern.test(line));
}

function detectNim(lines) {
  for (const line of lines.slice(0, 80)) {
    const match = line.match(/\b(?:NIM|NPM|NPM\.|NO\.?\s*MAHASISWA)\s*[:.]?\s*([A-Z0-9.-]{5,})\b/i);
    if (match) return match[1];
  }
  return null;
}

function cleanNameCandidate(value = '') {
  return normalizeText(value)
    .replace(/^NAMA\s*[:.]?\s*/i, '')
    .replace(/^OLEH\s*[:.]?\s*/i, '')
    .replace(/\bNIM\b.*$/i, '')
    .trim();
}

function looksLikePersonName(value = '') {
  const text = cleanNameCandidate(value);
  if (text.length < 4 || text.length > 80) return false;
  if (/\d/.test(text)) return false;
  if (/UNIVERSITAS|FAKULTAS|PROGRAM\s+STUDI|PROPOSAL|SKRIPSI|PENELITIAN|DIAJUKAN|PEMBIMBING/i.test(text)) return false;
  const words = text.split(/\s+/);
  return words.length >= 2 && words.length <= 6;
}

function detectStudentName(lines, nim) {
  for (const line of lines.slice(0, 80)) {
    const direct = line.match(/^NAMA\s*[:.]\s*(.+)$/i);
    if (direct && looksLikePersonName(direct[1])) return cleanNameCandidate(direct[1]);
  }

  const nimIndex = nim ? lines.findIndex((line) => line.includes(nim)) : -1;
  if (nimIndex >= 0) {
    for (const offset of [-3, -2, -1, 1, 2]) {
      const candidate = lines[nimIndex + offset];
      if (candidate && looksLikePersonName(candidate)) return cleanNameCandidate(candidate);
    }
  }

  const olehIndex = findLineIndex(lines.slice(0, 60), /^OLEH\b/i);
  if (olehIndex >= 0) {
    for (let index = olehIndex + 1; index <= olehIndex + 3; index += 1) {
      if (lines[index] && looksLikePersonName(lines[index])) return cleanNameCandidate(lines[index]);
    }
  }

  return null;
}

function titleScore(line) {
  const text = normalizeText(line);
  if (text.length < 20 || text.length > 220) return -99;
  if (/UNIVERSITAS|FAKULTAS|PROGRAM\s+STUDI|PROPOSAL|SKRIPSI|PENELITIAN|DIAJUKAN|OLEH|NIM|TAHUN\s+AKADEMIK/i.test(text)) return -50;

  let score = 0;
  if (text.length >= 35 && text.length <= 180) score += 3;
  if (/PENGARUH|ANALISIS|HUBUNGAN|IMPLEMENTASI|PERANCANGAN|STRATEGI|DAMPAK|EVALUASI|PENGEMBANGAN|EFEKTIVITAS/i.test(text)) score += 6;

  const letters = text.replace(/[^A-Za-zÀ-ÿ]/g, '');
  if (letters) {
    const upper = letters.replace(/[^A-ZÀ-Þ]/g, '').length / letters.length;
    if (upper > 0.7) score += 3;
  }

  if (/\bTERHADAP\b|\bPADA\b|\bDENGAN\b|\bMENGGUNAKAN\b/i.test(text)) score += 2;
  return score;
}

function detectTitle(lines) {
  const candidates = lines.slice(0, 60)
    .map((line, index) => ({ line: normalizeText(line), index, score: titleScore(line) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.index - b.index);

  return candidates[0]?.line || null;
}

function detectResearchType(fullText) {
  const sample = fullText.slice(0, 100000);
  if (/mixed\s*method|metode\s+campuran/i.test(sample)) return 'mixed';
  if (/penelitian\s+kualitatif|pendekatan\s+kualitatif|metode\s+kualitatif/i.test(sample)) return 'qualitative';
  if (/penelitian\s+kuantitatif|pendekatan\s+kuantitatif|metode\s+kuantitatif/i.test(sample)) return 'quantitative';
  return null;
}

function detectKeywords(paragraphs) {
  for (const paragraph of paragraphs) {
    const match = paragraph.text_content.match(/^(?:KATA\s+KUNCI|KEYWORDS?)\s*[:\-]\s*(.+)$/i);
    if (!match) continue;

    return match[1]
      .split(/[,;]+/)
      .map((item) => normalizeText(item))
      .filter(Boolean)
      .slice(0, 12);
  }

  return [];
}

function detectAbstract(paragraphs) {
  const headingIndex = paragraphs.findIndex((paragraph) =>
    /^(ABSTRAK|ABSTRACT)$/i.test(normalizeText(paragraph.text_content))
  );

  if (headingIndex < 0) return null;

  const chunks = [];
  for (let index = headingIndex + 1; index < paragraphs.length; index += 1) {
    const paragraph = paragraphs[index];
    const text = normalizeText(paragraph.text_content);

    if (!text) continue;
    if (/^(KATA\s+KUNCI|KEYWORDS?)\b/i.test(text)) break;
    if (paragraph.paragraph_type === 'heading' && chunks.length) break;
    if (detectSectionCode(text) && chunks.length) break;

    chunks.push(text);
    if (chunks.join(' ').length > 5000) break;
  }

  return chunks.length ? chunks.join('\n\n') : null;
}

function defaultProposalSections() {
  return [
    { section_code: 'BAB I', section_title: 'Pendahuluan', section_type: 'chapter', sort_order: 10 },
    { section_code: 'BAB II', section_title: 'Kajian Pustaka', section_type: 'chapter', sort_order: 20 },
    { section_code: 'BAB III', section_title: 'Metode Penelitian', section_type: 'chapter', sort_order: 30 },
    { section_code: 'REFERENSI', section_title: 'Daftar Pustaka', section_type: 'reference', sort_order: 40 },
  ];
}

export async function sha256Hex(arrayBuffer) {
  const digest = await crypto.subtle.digest('SHA-256', arrayBuffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

export async function parseProposalFile(file) {
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (!['docx', 'pdf'].includes(extension)) {
    throw new Error('Format proposal harus DOCX atau PDF.');
  }

  const arrayBuffer = await file.arrayBuffer();
  const parseResult = extension === 'docx'
    ? await parseDocx(arrayBuffer)
    : await parsePdf(arrayBuffer);

  const paragraphs = parseResult.paragraphs.map((paragraph, index) => ({
    ...paragraph,
    paragraph_index: index,
  }));

  const sections = attachSections(paragraphs);
  const fullText = paragraphs.map((paragraph) => paragraph.text_content).join('\n');
  const lines = paragraphs.map((paragraph) => paragraph.text_content).filter(Boolean);
  const nim = detectNim(lines);

  return {
    file,
    file_type: extension,
    file_size: file.size,
    file_hash: await sha256Hex(arrayBuffer),
    extracted_text: fullText,
    word_count: wordCount(fullText),
    paragraphs,
    sections: sections.length ? sections : defaultProposalSections(),
    metadata: {
      title: detectTitle(lines),
      nim,
      student_name: detectStudentName(lines, nim),
      research_type: detectResearchType(fullText),
      abstract: detectAbstract(paragraphs),
      keywords: detectKeywords(paragraphs),
    },
    warnings: parseResult.warnings || [],
  };
}
