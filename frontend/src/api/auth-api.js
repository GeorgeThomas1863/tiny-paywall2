import { fetchData, sendOperation } from "./request.js";

export const registerUser = async (email, password, displayName) =>
  sendOperation(
    "/auth/register",
    { method: "POST", body: { email, password, display_name: displayName } },
    "Registration failed"
  );

export const loginUser = async (email, password) =>
  sendOperation("/auth/login", { method: "POST", body: { email, password } }, "Login failed");

export const logoutUser = async () =>
  sendOperation("/auth/logout", { method: "POST" }, "Logout failed");

export const fetchMe = async () => fetchData("/auth/me");
