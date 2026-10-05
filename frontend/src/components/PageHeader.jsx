import React from 'react';

/** Consistent page heading: one h1, one supporting line, optional actions on the right. */
export default function PageHeader({ title, sub, actions, children }) {
  return (
    <header className="page-header">
      <div className="page-header__text">
        <h1 className="page-header__title">{title}</h1>
        {sub && <p className="page-header__sub">{sub}</p>}
        {children}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}
