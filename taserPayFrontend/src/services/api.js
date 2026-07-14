import axios from "axios";

const instance = axios.create ({
  baseURL: `${import.meta.env.VITE_API_URL ? import.meta.env.VITE_API_URL : "https://api.avapay.su/api/v1"}`,
  headers: import.meta.env.DEV ? {
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "69420",
  } : {
    "Content-Type": "application/json",
  },
  validateStatus: function (status) {
    return true;
  }
});

export default instance;
