import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import './App.css';
import { HeaderControls } from './components/common/HeaderControls';
import { UiLanguageProvider } from './contexts/UiLanguageContext';
import ChatPage from './pages/ChatPage';
import AnalysisPage from './pages/AnalysisPage';

// The analysis page sits under a header row holding the three menus
// (mode, language, theme) at the right. The chat page draws the same
// menus itself, at the top of its conversation column, so its history
// column can start at the very top (owner request 2026-09-26).
const HeaderLayout = () => (
  <>
    <header className="mx-auto flex w-full max-w-7xl items-center justify-end px-4 pt-4 md:px-6 lg:px-8">
      <HeaderControls />
    </header>
    <Outlet />
  </>
);

function App() {
  return (
    <UiLanguageProvider>
      <BrowserRouter>
        {/* A window-high column that scrolls as a whole: the analysis page
            grows past it and scrolls; the chat page fills it and scrolls
            inside its own two panels (owner request 2026-09-23). */}
        <div className="flex h-dvh flex-col overflow-y-auto bg-background text-foreground">
          <Routes>
            <Route element={<HeaderLayout />}>
              <Route path="/" element={<AnalysisPage />} />
            </Route>
            {/* The open conversation's id rides in the URL, so a refresh
                or a shared link lands on it (owner request 2026-10-13). */}
            <Route path="/chat/:conversationId?" element={<ChatPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </BrowserRouter>
    </UiLanguageProvider>
  );
}

export default App;
