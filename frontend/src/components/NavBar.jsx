import { Link } from 'react-router-dom'
import { formatCents } from '../format.js'

function NavBar({ user, onLogout }) {
  return (
    <nav>
      <Link to="/">tiny-paywall</Link>
      {user ? (
        <span>
          <Link to="/account">{formatCents(user.wallet_cents)}</Link>
          <Link to="/write">Write</Link>
          {user.is_admin && <Link to="/admin">Admin</Link>}
          {user.display_name}
          <button onClick={onLogout}>Logout</button>
        </span>
      ) : (
        <Link to="/login">Login</Link>
      )}
    </nav>
  )
}

export default NavBar
