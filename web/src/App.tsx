import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom';
import './App.css';
import { UiLanguageToggle } from './components/i18n/UiLanguageToggle';
import { ThemeToggle } from './components/theme/ThemeToggle';
import { UiLanguageProvider, useUiLanguage } from './contexts/UiLanguageContext';
import { cn } from './utils/cn';
import ChatbotPage from './pages/ChatbotPage';
import TieredAltPage from './pages/TieredAltPage';

const navClass = ({ isActive }: { isActive: boolean }) =>
  cn('text-sm transition', isActive ? 'font-semibold text-gray-200' : 'text-gray-500 hover:text-gray-300');

// The two pages side by side in the header: the analysis page and the
// chat about it.
const HeaderNav = () => {
  const { t } = useUiLanguage();
  return (
    <nav aria-label="Pages" className="flex items-center gap-4">
      <NavLink to="/" end className={navClass}>
        {t('chat.nav.analysis')}
      </NavLink>
      <NavLink to="/chatbot" className={navClass}>
        {t('chat.nav.chat')}
      </NavLink>
    </nav>
  );
};

function App() {
  return (
    <UiLanguageProvider>
      <BrowserRouter>
        <div className="min-h-screen bg-background text-foreground">
          <header className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 pt-4 md:px-6 lg:px-8">
            <div className="flex items-center gap-6">
              <span className="text-sm font-semibold tracking-wide text-gray-400">
                Custom Stock Analysis
              </span>
              <HeaderNav />
            </div>
            <div className="flex items-center gap-2">
              <UiLanguageToggle />
              <ThemeToggle />
            </div>
          </header>
          <Routes>
            <Route path="/" element={<TieredAltPage />} />
            <Route path="/chatbot" element={<ChatbotPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </BrowserRouter>
    </UiLanguageProvider>
  );
}

export default App;
