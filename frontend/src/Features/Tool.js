import axios from "axios";

export const fetchPages = () => {
  return axios.get("http://localhost:8000/pages")
    .then(res => res.data.pages || []);
};

export const fetchMessages = (selectedPage, conversationId) => {
  return axios.get(`http://localhost:8000/messages/${selectedPage}/${conversationId}`)
    .then(res => res.data.data || []);
};

export const sendMessage = (selectedPage, conversationId, newMessage) => {
  return axios.get(`http://localhost:8000/messages/${selectedPage}/${conversationId}`)
    .then(res => {
      const data = res.data.data || [];
      const recipient = data.find(msg => msg.from?.id !== selectedPage);
      const psid = recipient?.from?.id;
      if (!psid) throw new Error("ไม่พบ PSID ผู้รับ");
      return axios.post(`http://localhost:8000/send/${selectedPage}/${psid}`, {
        message: newMessage,
      });
    });
};

export const connectFacebook = () => {
  window.location.href = "http://localhost:8000/connect";
};