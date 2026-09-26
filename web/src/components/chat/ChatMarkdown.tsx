import { lazy, Suspense } from 'react';

const Inner = lazy(() => import('./ChatMarkdownInner'));

// The Markdown renderer arrives in its own chunk the first time a reply
// is shown; until then (and in the test DOM) the raw text stands in.
export const ChatMarkdown = ({ text }: { text: string }) => (
  <Suspense fallback={<p className="whitespace-pre-wrap">{text}</p>}>
    <Inner text={text} />
  </Suspense>
);
