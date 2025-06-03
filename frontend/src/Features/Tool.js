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

export async function saveMessageToDB(pageId, message) {
  const res = await fetch("http://localhost:8000/custom_message", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ page_id: pageId, message })
  });

  if (!res.ok) throw new Error("บันทึกข้อความไม่สำเร็จ");
  return res.json();
}

export async function getMessagesByPageId(pageId) {
  const res = await fetch(`http://localhost:8000/custom_messages/${pageId}`);
  if (!res.ok) throw new Error("โหลดข้อความไม่สำเร็จ");
  return res.json();
}

export async function deleteMessageFromDB(messageId) {
  const res = await fetch(`http://localhost:8000/custom_message/${messageId}`, {
    method: "DELETE"
  });
  if (!res.ok) throw new Error("ลบข้อความไม่สำเร็จ");
  return res.json();
}