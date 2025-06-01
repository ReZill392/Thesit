import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import '../CSS/Default.css';
import { fetchPages, connectFacebook } from "../Features/Tool";

function SetDefault() {
  const [pages, setPages] = useState([]);
  const [selectedPage, setSelectedPage] = useState("");
  const [messages, setMessages] = useState(() => {
    // โหลดข้อความจาก localStorage เมื่อเริ่มต้น
    const savedMessages = localStorage.getItem('defaultMessages');
    return savedMessages ? JSON.parse(savedMessages) : [];
  });
  const [newMessage, setNewMessage] = useState("");

  useEffect(() => {
    fetchPages()
      .then(setPages)
      .catch(err => console.error("ไม่สามารถโหลดเพจได้:", err));
  }, []);

  // บันทึกข้อความลง localStorage ทุกครั้งที่ messages เปลี่ยนแปลง
  useEffect(() => {
    localStorage.setItem('defaultMessages', JSON.stringify(messages));
  }, [messages]);

  const handleAddMessage = () => {
    if (newMessage.trim()) {
      setMessages([...messages, newMessage]);
      setNewMessage("");
    }
  };

  const handleDeleteMessage = (index) => {
    const updatedMessages = messages.filter((_, i) => i !== index);
    setMessages(updatedMessages);
  };

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <h3 className="sidebar-title">ช่องทางเชื่อมต่อ</h3>
        <button onClick={connectFacebook} className="BT">
          <svg width="15" height="20" viewBox="0 0 320 512" fill="#fff" className="fb-icon">
            <path d="M279.14 288l14.22-92.66h-88.91V127.91c0-25.35 12.42-50.06 52.24-50.06H293V6.26S259.5 0 225.36 0c-73.22 0-121 44.38-121 124.72v70.62H22.89V288h81.47v224h100.2V288z" />
          </svg>
        </button>
        <hr />
        <select
          value={selectedPage}
          onChange={(e) => setSelectedPage(e.target.value)}
          className="select-page"
        >
          <option value="">-- เลือกเพจ --</option>
          {pages.map((page) => (
            <option key={page.id} value={page.id}>
              {page.name}
            </option>
          ))}
        </select>
        <Link to="/App" className="title" style={{marginLeft:"64px"}}>หน้าแรก</Link><br />
        <Link to="/Set_Miner" className="title" style={{marginLeft:"50px"}}>ตั้งค่าระบบขุด</Link><br />
        <a href="#" className="title" style={{marginLeft:"53px"}}>Dashboard</a><br />
        <a href="#" className="title" style={{marginLeft:"66px"}}>Setting</a><br />    
      </aside>

      {/* Main Content */}
      <div className="message-settings-container">
        <h1>ตั้งค่าชุดข้อความ Default</h1>
        
        <div className="message-list">
          {messages.length > 0 ? (
            messages.map((msg, index) => (
              <div key={index} className="message-item">
                <span>{msg}</span>
                <button 
                  onClick={() => handleDeleteMessage(index)}
                  className="delete-button"
                >
                  ลบ
                </button>
              </div>
            ))
          ) : (
            <p className="no-messages">ยังไม่มีข้อความที่บันทึกไว้</p>
          )}
        </div>

        <div className="message-input-group">
          <textarea
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            placeholder="เพิ่มข้อความใหม่..."
            className="message-textarea"
          />
          <button 
            onClick={handleAddMessage}
            className="add-button"
            disabled={!newMessage.trim()}
          >
            เพิ่มข้อความ
          </button>
        </div>

        <Link to="/Set_Miner" className="back-button">
          กลับไปหน้าก่อนหน้า
        </Link>
      </div>
    </div>
  );
}

export default SetDefault;