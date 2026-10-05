import React from 'react';
import { SCOPE_NOTICE } from '../utils/copy';

/** The one sentence that must appear wherever results are shown. */
export default function ScopeNotice({ compact = false }) {
  return (
    <p
      role="note"
      className={compact ? 'scope-notice scope-notice--compact' : 'scope-notice'}
    >
      {SCOPE_NOTICE}
    </p>
  );
}
