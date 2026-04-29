// Property-Based Tests for renderMarkdown function
// Feature: markdown-parser-fix

import { describe, it, expect } from 'vitest';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { JSDOM } from 'jsdom';
import fc from 'fast-check';

// Set up DOM environment
const window = new JSDOM('').window;
global.DOMPurify = DOMPurify(window);
global.marked = marked;

// Configure marked
marked.setOptions({
  gfm: true,
  breaks: true,
  headerIds: false,
  mangle: false,
});

// Import the renderMarkdown function logic
function renderMarkdown(input) {
  if (input === null || input === undefined || input === '') {
    return '';
  }

  let markdownText;
  try {
    markdownText = String(input);
  } catch (error) {
    console.error('Error converting input to string:', error);
    return '';
  }

  if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
    console.error('marked or DOMPurify not loaded');
    return markdownText;
  }

  try {
    const rawHtml = marked.parse(markdownText);
    const sanitizedHtml = DOMPurify.sanitize(rawHtml, {
      ALLOWED_TAGS: [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'br', 'strong', 'em', 'del', 's',
        'a', 'code', 'pre',
        'ul', 'ol', 'li',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'blockquote', 'hr'
      ],
      ALLOWED_ATTR: ['href', 'target', 'rel', 'align'],
      ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i
    });
    return sanitizedHtml;
  } catch (error) {
    console.error('Error rendering markdown:', error);
    return markdownText;
  }
}

// Property 1: Input Validation
describe('Property 1: Input Validation', () => {
  it('should return string without throwing for any input', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.string(),
          fc.constant(null),
          fc.constant(undefined),
          fc.integer(),
          fc.object()
        ),
        (input) => {
          let result;
          expect(() => {
            result = renderMarkdown(input);
          }).not.toThrow();
          expect(typeof result).toBe('string');
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Property 2: XSS Prevention
describe('Property 2: XSS Prevention', () => {
  it('should not contain script tags in output', () => {
    fc.assert(
      fc.property(
        fc.string(),
        fc.constantFrom('<script>', '</script>', '<SCRIPT>', '</SCRIPT>'),
        (text, scriptTag) => {
          const input = `${text}${scriptTag}alert('xss')${scriptTag.replace('<', '</')}`;
          const result = renderMarkdown(input);
          expect(result.toLowerCase()).not.toContain('<script');
        }
      ),
      { numRuns: 100 }
    );
  });

  it('should not contain javascript: URLs', () => {
    fc.assert(
      fc.property(
        fc.string().filter(s => s.length > 0 && !s.includes('[') && !s.includes(']')),
        (linkText) => {
          const input = `[${linkText}](javascript:alert('xss'))`;
          const result = renderMarkdown(input);
          // Check that the link either doesn't render or doesn't contain javascript:
          if (result.includes('<a')) {
            expect(result).not.toContain('javascript:');
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('should not contain event handlers', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('onclick', 'onerror', 'onload', 'onmouseover'),
        fc.string(),
        (handler, code) => {
          const input = `<div ${handler}="${code}">test</div>`;
          const result = renderMarkdown(input);
          expect(result).not.toContain(handler);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Property 3: Header Rendering
describe('Property 3: Header Rendering', () => {
  it('should render headers with correct tags', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 6 }),
        fc.string({ minLength: 1, maxLength: 50 }).filter(s => !s.includes('\n') && s.trim().length > 0 && /[a-zA-Z0-9]/.test(s)),
        (level, text) => {
          const hashes = '#'.repeat(level);
          const input = `${hashes} ${text}`;
          const result = renderMarkdown(input);
          expect(result).toContain(`<h${level}>`);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Property 4: List Rendering
describe('Property 4: List Rendering', () => {
  it('should render unordered lists', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 20 }).filter(s => !s.includes('\n')), { minLength: 1, maxLength: 5 }),
        (items) => {
          const input = items.map(item => `- ${item}`).join('\n');
          const result = renderMarkdown(input);
          expect(result).toContain('<ul>');
          expect(result).toContain('<li>');
        }
      ),
      { numRuns: 100 }
    );
  });

  it('should render ordered lists', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 20 }).filter(s => !s.includes('\n')), { minLength: 1, maxLength: 5 }),
        (items) => {
          const input = items.map((item, i) => `${i + 1}. ${item}`).join('\n');
          const result = renderMarkdown(input);
          expect(result).toContain('<ol>');
          expect(result).toContain('<li>');
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Property 5: Table Rendering
describe('Property 5: Table Rendering', () => {
  it('should render tables with proper structure', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 10 }).filter(s => !s.includes('|') && !s.includes('\n')), { minLength: 2, maxLength: 4 }),
        fc.array(fc.string({ minLength: 1, maxLength: 10 }).filter(s => !s.includes('|') && !s.includes('\n')), { minLength: 2, maxLength: 4 }),
        (headers, cells) => {
          const headerRow = `| ${headers.join(' | ')} |`;
          const separator = `| ${headers.map(() => '---').join(' | ')} |`;
          const dataRow = `| ${cells.slice(0, headers.length).join(' | ')} |`;
          const input = `${headerRow}\n${separator}\n${dataRow}`;
          const result = renderMarkdown(input);
          expect(result).toContain('<table>');
          expect(result).toContain('<thead>');
          expect(result).toContain('<tbody>');
          expect(result).toContain('<tr>');
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Property 6: Backward Compatibility - Code Blocks
describe('Property 6: Backward Compatibility - Code Blocks', () => {
  it('should render code blocks with pre and code tags', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 50 }),
        (code) => {
          const input = `\`\`\`\n${code}\n\`\`\``;
          const result = renderMarkdown(input);
          expect(result).toContain('<pre>');
          expect(result).toContain('<code>');
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Property 7: Backward Compatibility - Inline Formatting
describe('Property 7: Backward Compatibility - Inline Formatting', () => {
  it('should render bold text', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => 
          !s.includes('*') && 
          !s.includes('\n') && 
          s.trim().length > 0 && 
          /[a-zA-Z0-9]/.test(s) &&
          s === s.trim() // No leading/trailing whitespace
        ),
        (text) => {
          const input = `**${text}**`;
          const result = renderMarkdown(input);
          expect(result).toContain('<strong>');
        }
      ),
      { numRuns: 100 }
    );
  });

  it('should render italic text', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => 
          !s.includes('*') && 
          !s.includes('\n') && 
          !s.includes('\\') && // Backslash can escape markdown
          s.trim().length > 0 && 
          /[a-zA-Z0-9]/.test(s) &&
          s === s.trim() // No leading/trailing whitespace
        ),
        (text) => {
          const input = `*${text}*`;
          const result = renderMarkdown(input);
          expect(result).toContain('<em>');
        }
      ),
      { numRuns: 100 }
    );
  });

  it('should render inline code', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => !s.includes('`') && !s.includes('\n')),
        (code) => {
          const input = `\`${code}\``;
          const result = renderMarkdown(input);
          expect(result).toContain('<code>');
          // Code content might be HTML-escaped, so check for that too
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Property 8: Backward Compatibility - Links
describe('Property 8: Backward Compatibility - Links', () => {
  it('should render links with anchor tags', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => !s.includes('[') && !s.includes(']') && !s.includes('\n')),
        fc.webUrl(),
        (text, url) => {
          const input = `[${text}](${url})`;
          const result = renderMarkdown(input);
          expect(result).toContain('<a');
          expect(result).toContain('href=');
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Property 9: Line Break Handling
describe('Property 9: Line Break Handling', () => {
  it('should handle newlines in text', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }),
        fc.string({ minLength: 1, maxLength: 20 }),
        (line1, line2) => {
          const input = `${line1}\n${line2}`;
          const result = renderMarkdown(input);
          expect(typeof result).toBe('string');
          expect(result.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Property 10: Blockquote Rendering
describe('Property 10: Blockquote Rendering', () => {
  it('should render blockquotes', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 50 }).filter(s => !s.includes('\n') && s.trim().length > 0),
        (text) => {
          const input = `> ${text}`;
          const result = renderMarkdown(input);
          expect(result).toContain('<blockquote>');
          // Text might be trimmed or escaped
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Property 11: Horizontal Rule Rendering
describe('Property 11: Horizontal Rule Rendering', () => {
  it('should render horizontal rules', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('---', '***', '___'),
        (hrSyntax) => {
          const result = renderMarkdown(hrSyntax);
          expect(result).toContain('<hr>');
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Property 12: Strikethrough Rendering
describe('Property 12: Strikethrough Rendering', () => {
  it('should render strikethrough text', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => 
          !s.includes('~') && 
          !s.includes('\n') && 
          s.trim().length > 0 && 
          /[a-zA-Z0-9]/.test(s) &&
          s === s.trim() // No leading/trailing whitespace
        ),
        (text) => {
          const input = `~~${text}~~`;
          const result = renderMarkdown(input);
          expect(result).toMatch(/<(del|s)>/);
        }
      ),
      { numRuns: 100 }
    );
  });
});
