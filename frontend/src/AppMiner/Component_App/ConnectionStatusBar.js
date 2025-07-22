// components/ConnectionStatusBar.js
// =====================================================
// COMPONENT: ConnectionStatusBar
// PURPOSE: แสดงสถานะการเชื่อมต่อและเวลาอัพเดท
// FEATURES:
// - แสดงสถานะการเชื่อมต่อเพจ
// - แสดงเวลาอัพเดทล่าสุด
// - มีปุ่ม Sync ข้อมูล
// - แสดงเวลาปัจจุบัน
// =====================================================

import React from 'react';
import SyncCustomersButton from '../Component_App/SyncCustomersButton';
import DateFilterBadge from '../Component_App/DateFilterBadge';

const ConnectionStatusBar = ({ 
  selectedPage, 
  selectedPageInfo, 
  lastUpdateTime, 
  currentTime,
  onSyncComplete,
  syncDateRange,
  onClearDateFilter
}) => {
  const getUpdateStatus = () => {
    const diffMs = currentTime - lastUpdateTime;
    const diffMin = Math.floor(diffMs / 60000);
    
    if (diffMin < 1) return { status: "อัพเดทล่าสุด", color: "success" };
    if (diffMin < 5) return { status: `${diffMin} นาทีที่แล้ว`, color: "warning" };
    return { status: `${diffMin} นาทีที่แล้ว`, color: "danger" };
  };

  const updateStatus = getUpdateStatus();

  return (
    <div className="connection-status-bar">
      <div className="status-left">
        <div className={`connection-badge ${selectedPage ? 'connected' : 'disconnected'}`}>
          <span className="status-icon">{selectedPage ? '🟢' : '🔴'}</span>
          <span className="status-text">
            {selectedPage ? `เชื่อมต่อแล้ว: ${selectedPageInfo?.name}` : 'ยังไม่ได้เชื่อมต่อ'}
          </span>
        </div>
        
        <div className={`update-badge ${updateStatus.color}`}>
          <span className="update-icon">🔄</span>
          <span className="update-text">{updateStatus.status}</span>
        </div>
        
        {selectedPage && (
          <SyncCustomersButton 
            selectedPage={selectedPage}
            onSyncComplete={onSyncComplete}
          />
        )}

        <DateFilterBadge 
          dateRange={syncDateRange}
          onClear={onClearDateFilter}
        />
      </div>
      
      <div className="status-right">
        <span className="clock-display">
          🕐 {currentTime.toLocaleTimeString('th-TH')}
        </span>
      </div>
    </div>
  );
};

export default ConnectionStatusBar;