import axios from "axios";

const instance = axios.create ({
  // Baked at image build time. Production default must stay api.avapay.net
  // so a rebuild without .env does not hang on the old api.avapay.su host.
  baseURL: `${import.meta.env.VITE_API_URL || "https://api.avapay.net/api/v1"}`,
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
