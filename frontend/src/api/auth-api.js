import { sendRequest, extractErrorMessage } from "./request.js";

export const registerUser = async (email, password, displayName) => {
  const { status, data } = await sendRequest("/auth/register", {
    method: "POST",
    body: { email, password, display_name: displayName },
  });
  if (status !== 200) {
    return { success: false, message: extractErrorMessage(data, "Registration failed") };
  }
  return data;
};

export const loginUser = async (email, password) => {
  const { status, data } = await sendRequest("/auth/login", {
    method: "POST",
    body: { email, password },
  });
  if (status !== 200) {
    return { success: false, message: extractErrorMessage(data, "Login failed") };
  }
  return data;
};

export const logoutUser = async () => {
  const { status, data } = await sendRequest("/auth/logout", { method: "POST" });
  if (status !== 200) {
    return { success: false, message: extractErrorMessage(data, "Logout failed") };
  }
  return data;
};

export const fetchMe = async () => {
  const { status, data } = await sendRequest("/auth/me");
  if (status !== 200) return null;
  return data;
};
