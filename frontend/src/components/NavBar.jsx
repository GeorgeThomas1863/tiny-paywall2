import { Link } from 'react-router-dom'
import { avatarGradient, formatCents } from '../format.js'

function NavBar({ user, onLogout }) {
  return (
    <nav className="topbar">
      <Link to="/" className="brand">
        tiny<b>paywall</b>
      </Link>
      <span className="topbar-links">
        {user ? (
          <>
            <Link to="/account" className="wallet-chip">
              {formatCents(user.wallet_cents)}
            </Link>
            <Link to="/write" className="accent-btn">
              Write
            </Link>
            {user.is_admin && <Link to="/admin">Admin</Link>}
            <Link to="/account" className="user-chip">
              <span
                className="avatar"
                style={avatarGradient(user.display_name)}
                aria-hidden="true"
              />
              {user.display_name}
            </Link>
            <button onClick={onLogout} className="ghost-btn">
              Logout
            </button>
          </>
        ) : (
          <Link to="/login" className="accent-btn">
            Login
          </Link>
        )}
      </span>
    </nav>
  )
}

export default NavBar
