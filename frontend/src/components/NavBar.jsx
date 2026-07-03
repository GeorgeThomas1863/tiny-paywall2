import { Link } from 'react-router-dom'

function NavBar({ user, onLogout }) {
  return (
    <nav>
      <Link to="/">tiny-paywall</Link>
      {user ? (
        <span>
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
