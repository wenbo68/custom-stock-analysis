import type React from 'react';
import { HeaderMenu } from '../common/HeaderMenu';
import { useModeChoice } from './useModeChoice';

/** The mode dropdown in the header. */
export const ModeToggle: React.FC = () => <HeaderMenu {...useModeChoice()} testId="mode-menu" />;
