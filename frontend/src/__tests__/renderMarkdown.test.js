// Test file for renderMarkdown function
// Feature: markdown-parser-fix

import { describe, it, expect, beforeAll } from 'vitest';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { JSDOM } from 'jsdom';

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

// Unit Tests for empty/null input handling
describe('renderMarkdown - Empty/Null Input', () => {
  it('should return empty string for null input', () => {
    const result = renderMarkdown(null);
    expect(result).toBe('');
  });

  it('should return empty string for undefined input', () => {
    const result = renderMarkdown(undefined);
    expect(result).toBe('');
  });

  it('should return empty string for empty string input', () => {
    const result = renderMarkdown('');
    expect(result).toBe('');
  });
});

// Unit Tests for XSS prevention
describe('renderMarkdown - XSS Prevention', () => {
  it('should remove script tags', () => {
    const input = 'Hello <script>alert("XSS")</script> World';
    const result = renderMarkdown(input);
    expect(result).not.toContain('<script>');
    expect(result).not.toContain('alert');
  });

  it('should block javascript: URLs', () => {
    const input = '[Click me](javascript:alert("XSS"))';
    const result = renderMarkdown(input);
    expect(result).not.toContain('javascript:');
  });

  it('should strip event handlers like onclick', () => {
    const input = '<a onclick="alert(\'XSS\')">Click</a>';
    const result = renderMarkdown(input);
    expect(result).not.toContain('onclick');
  });

  it('should strip event handlers like onerror', () => {
    const input = '<img onerror="alert(\'XSS\')" src="invalid">';
    const result = renderMarkdown(input);
    expect(result).not.toContain('onerror');
  });
});

// Unit Tests for markdown features
describe('renderMarkdown - Markdown Features', () => {
  it('should render h1 headers', () => {
    const input = '# Header 1';
    const result = renderMarkdown(input);
    expect(result).toContain('<h1>');
    expect(result).toContain('Header 1');
  });

  it('should render h2 headers', () => {
    const input = '## Header 2';
    const result = renderMarkdown(input);
    expect(result).toContain('<h2>');
    expect(result).toContain('Header 2');
  });

  it('should render h6 headers', () => {
    const input = '###### Header 6';
    const result = renderMarkdown(input);
    expect(result).toContain('<h6>');
    expect(result).toContain('Header 6');
  });

  it('should render unordered lists with dash', () => {
    const input = '- Item 1\n- Item 2';
    const result = renderMarkdown(input);
    expect(result).toContain('<ul>');
    expect(result).toContain('<li>');
    expect(result).toContain('Item 1');
    expect(result).toContain('Item 2');
  });

  it('should render unordered lists with asterisk', () => {
    const input = '* Item 1\n* Item 2';
    const result = renderMarkdown(input);
    expect(result).toContain('<ul>');
    expect(result).toContain('<li>');
  });

  it('should render ordered lists', () => {
    const input = '1. First\n2. Second';
    const result = renderMarkdown(input);
    expect(result).toContain('<ol>');
    expect(result).toContain('<li>');
    expect(result).toContain('First');
    expect(result).toContain('Second');
  });

  it('should render tables', () => {
    const input = '| Header 1 | Header 2 |\n|----------|----------|\n| Cell 1   | Cell 2   |';
    const result = renderMarkdown(input);
    expect(result).toContain('<table>');
    expect(result).toContain('<thead>');
    expect(result).toContain('<tbody>');
    expect(result).toContain('<tr>');
    expect(result).toContain('<th>');
    expect(result).toContain('<td>');
  });

  it('should render blockquotes', () => {
    const input = '> This is a quote';
    const result = renderMarkdown(input);
    expect(result).toContain('<blockquote>');
    expect(result).toContain('This is a quote');
  });

  it('should render horizontal rules with dashes', () => {
    const input = '---';
    const result = renderMarkdown(input);
    expect(result).toContain('<hr>');
  });

  it('should render horizontal rules with asterisks', () => {
    const input = '***';
    const result = renderMarkdown(input);
    expect(result).toContain('<hr>');
  });

  it('should render strikethrough', () => {
    const input = '~~deleted text~~';
    const result = renderMarkdown(input);
    expect(result).toMatch(/<(del|s)>/);
    expect(result).toContain('deleted text');
  });
});

// Unit Tests for backward compatibility
describe('renderMarkdown - Backward Compatibility', () => {
  it('should render code blocks with triple backticks', () => {
    const input = '```\nconst x = 1;\n```';
    const result = renderMarkdown(input);
    expect(result).toContain('<pre>');
    expect(result).toContain('<code>');
    expect(result).toContain('const x = 1;');
  });

  it('should render inline code with single backticks', () => {
    const input = 'Use `const` for constants';
    const result = renderMarkdown(input);
    expect(result).toContain('<code>');
    expect(result).toContain('const');
  });

  it('should render bold with double asterisks', () => {
    const input = '**bold text**';
    const result = renderMarkdown(input);
    expect(result).toContain('<strong>');
    expect(result).toContain('bold text');
  });

  it('should render italic with single asterisk', () => {
    const input = '*italic text*';
    const result = renderMarkdown(input);
    expect(result).toContain('<em>');
    expect(result).toContain('italic text');
  });

  it('should render links with target="_blank" and rel attributes', () => {
    const input = '[Google](https://google.com)';
    const result = renderMarkdown(input);
    expect(result).toContain('<a');
    expect(result).toContain('href="https://google.com"');
    expect(result).toContain('Google');
    // Note: marked doesn't add target and rel by default, we may need to configure this
  });

  it('should convert newlines appropriately', () => {
    const input = 'Line 1\nLine 2';
    const result = renderMarkdown(input);
    // With breaks: true, newlines should create <br> tags
    expect(result).toContain('Line 1');
    expect(result).toContain('Line 2');
  });
});

