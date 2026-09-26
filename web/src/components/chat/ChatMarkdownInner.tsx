import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '../../utils/cn';
import { ALT_LINK } from '../analysis/styles';
import { CHAT_SURFACE_1 } from './chatSurfaces';

// The bot's replies are Markdown (bold, lists, code spans). Rendered
// with the alt page's type: body gray-300, emphasis gray-200. Loaded
// lazily (ChatMarkdown.tsx) so the analysis page never pays for it.
const ChatMarkdownInner = ({ text }: { text: string }) => (
  <Markdown
    remarkPlugins={[remarkGfm]}
    components={{
      p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
      ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
      ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
      li: ({ children }) => <li className="leading-relaxed">{children}</li>,
      strong: ({ children }) => <strong className="font-semibold text-ink-1">{children}</strong>,
      h1: ({ children }) => <p className="my-2 font-semibold text-ink-1">{children}</p>,
      h2: ({ children }) => <p className="my-2 font-semibold text-ink-1">{children}</p>,
      h3: ({ children }) => <p className="my-2 font-semibold text-ink-1">{children}</p>,
      h4: ({ children }) => <p className="my-2 font-semibold text-ink-1">{children}</p>,
      hr: () => <hr className="my-3 border-border/60" />,
      code: ({ children }) => (
        <code className={cn('rounded px-1 py-0.5 text-[12px] text-ink-1', CHAT_SURFACE_1)}>{children}</code>
      ),
      pre: ({ children }) => (
        <pre className={cn('my-2 overflow-x-auto rounded p-3 text-[12px] text-ink-2', CHAT_SURFACE_1)}>{children}</pre>
      ),
      a: ({ children, href }) => (
        <a href={href} target="_blank" rel="noreferrer" className={ALT_LINK}>
          {children}
        </a>
      ),
      table: ({ children }) => (
        <div className="my-2 overflow-x-auto">
          <table className="text-left text-xs">{children}</table>
        </div>
      ),
      th: ({ children }) => <th className="pr-4 pb-1 font-semibold text-ink-1">{children}</th>,
      td: ({ children }) => <td className="pr-4 py-0.5 align-top">{children}</td>,
    }}
  >
    {text}
  </Markdown>
);

export default ChatMarkdownInner;
