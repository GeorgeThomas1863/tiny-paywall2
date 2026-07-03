const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const sendRequest = async (path, options = {}) => {
  const { method = "GET", body = null } = options;

  const fetchParams = { method, credentials: "include" };
  if (body) {
    fetchParams.headers = { "Content-Type": "application/json" };
    fetchParams.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(`${API_URL}${path}`, fetchParams);
    const data = await parseResponseJson(response);
    return { status: response.status, data };
  } catch (e) {
    console.log("API REQUEST FAILED: " + path, e.message);
    return { status: 0, data: null };
  }
};

export const fetchData = async (path) => {
  const { status, data } = await sendRequest(path);
  if (status !== 200) return null;
  return data;
};

export const sendOperation = async (path, options, fallbackMessage) => {
  const { status, data } = await sendRequest(path, options);
  if (status !== 200) {
    return { success: false, message: extractErrorMessage(data, fallbackMessage) };
  }
  return data;
};

export const extractErrorMessage = (data, fallback) => {
  if (!data) return fallback;
  if (typeof data.detail === "string") return data.detail;
  if (typeof data.message === "string") return data.message;
  return fallback;
};

//---

const parseResponseJson = async (response) => {
  try {
    return await response.json();
  } catch {
    return null;
  }
};
