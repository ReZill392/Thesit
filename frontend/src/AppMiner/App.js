// =====================================================
// REFACTORED APP.JS - แบ่งเป็น Component ย่อยๆ
// =====================================================

import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
import '../CSS/App.css';
import { fetchPages, getMessagesBySetId, fetchConversations } from "../Features/Tool";
import Sidebar from "./Sidebar"; 
import Popup from "./Component_App/MinerPopup";
import SyncCustomersButton from './Component_App/SyncCustomersButton';
import DateFilterBadge from './Component_App/DateFilterBadge';

// Import component ย่อยที่แยกออกมา
import TimeAgoCell from './Component_App/TimeAgoCell';
import CustomerInfoBadge from './Component_App/CustomerInfoBadge';
import CustomerStatistics from './Component_App/CustomerStatistics';
import ConversationRow from './Component_App/ConversationRow';
import FileUploadSection from './Component_App/FileUploadSection';
import HeroSection from './Component_App/HeroSection';
import ConnectionStatusBar from './Component_App/ConnectionStatusBar';
import FilterSection from './Component_App/FilterSection';
import AlertMessages from './Component_App/AlertMessages';
import ConversationTable from './Component_App/ConversationTable';
import ActionBar from './Component_App/ActionBar';
import LoadingState from './Component_App/LoadingState';
import EmptyState from './Component_App/EmptyState';
import DailyMiningLimit from './Component_App/DailyMiningLimit';

// =====================================================
// MAIN APP COMPONENT
// =====================================================
function App() {
  // State Management
  const [pages, setPages] = useState([]);
  const [selectedPage, setSelectedPage] = useState("");
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showFilter, setShowFilter] = useState(false);
  
  // Filter States
  const [filters, setFilters] = useState({
    disappearTime: "",
    startDate: "",
    endDate: "",
    customerType: "",
    platformType: "",
    miningStatus: ""
  });
  
  const [allConversations, setAllConversations] = useState([]);
  const [filteredConversations, setFilteredConversations] = useState([]);
  const [pageId, setPageId] = useState("");
  const [selectedConversationIds, setSelectedConversationIds] = useState([]);
  const [defaultMessages, setDefaultMessages] = useState([]);
  const [isPopupOpen, setIsPopupOpen] = useState(false);
  const [selectedMessageSetIds, setSelectedMessageSetIds] = useState([]);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [lastUpdateTime, setLastUpdateTime] = useState(new Date());
  const [syncDateRange, setSyncDateRange] = useState(null);
  const [userInactivityData, setUserInactivityData] = useState({});
  
  // Daily Mining Limit States
  const [dailyMiningLimit, setDailyMiningLimit] = useState(() => {
    const saved = localStorage.getItem('dailyMiningLimit');
    return saved ? parseInt(saved) : 100;
  });
  const [todayMiningCount, setTodayMiningCount] = useState(() => {
    const savedData = localStorage.getItem('miningData');
    if (savedData) {
      const data = JSON.parse(savedData);
      const today = new Date().toDateString();
      if (data.date === today) {
        return data.count;
      }
    }
    return 0;
  });
  
  // Refs
  const inactivityUpdateTimerRef = useRef(null);
  const clockIntervalRef = useRef(null);
  const messageCache = useRef({});
  const cacheTimeout = 5 * 60 * 1000;

  // Utility Functions
  const getCachedData = (key, cache) => {
    const cached = cache.current[key];
    if (cached && Date.now() - cached.timestamp < cacheTimeout) {
      return cached.data;
    }
    return null;
  };

  const setCachedData = (key, data, cache) => {
    cache.current[key] = {
      data,
      timestamp: Date.now()
    };
  };

  // Mining Count Functions
  const updateMiningCount = (count) => {
    const today = new Date().toDateString();
    const newCount = todayMiningCount + count;
    setTodayMiningCount(newCount);
    
    localStorage.setItem('miningData', JSON.stringify({
      date: today,
      count: newCount
    }));
  };

  const resetDailyCount = () => {
    const today = new Date().toDateString();
    const savedData = localStorage.getItem('miningData');
    
    if (savedData) {
      const data = JSON.parse(savedData);
      if (data.date !== today) {
        setTodayMiningCount(0);
        localStorage.setItem('miningData', JSON.stringify({
          date: today,
          count: 0
        }));
      }
    }
  };

  const canMineMore = () => {
    return todayMiningCount < dailyMiningLimit;
  };

  const getRemainingMines = () => {
    return Math.max(0, dailyMiningLimit - todayMiningCount);
  };

  // Computed Values
  const displayData = useMemo(() => {
    return filteredConversations.length > 0 ? filteredConversations : conversations;
  }, [filteredConversations, conversations]);

  const selectedPageInfo = pages.find(p => p.id === selectedPage);

  // Callback Functions
  const handleInactivityChange = useCallback((userId, minutes) => {
    setUserInactivityData(prev => ({
      ...prev,
      [userId]: {
        minutes,
        updatedAt: new Date()
      }
    }));
  }, []);

  const toggleCheckbox = useCallback((conversationId) => {
    setSelectedConversationIds((prev) =>
      prev.includes(conversationId)
        ? prev.filter((id) => id !== conversationId)
        : [...prev, conversationId]
    );
  }, []);

  // Data Loading Functions
  const loadMessages = async (pageId) => {
    const cached = getCachedData(`messages_${pageId}`, messageCache);
    if (cached) {
      setDefaultMessages(cached);
      return cached;
    }

    try {
      const data = await getMessagesBySetId(pageId);
      const messages = Array.isArray(data) ? data : [];
      setDefaultMessages(messages);
      setCachedData(`messages_${pageId}`, messages, messageCache);
      return messages;
    } catch (err) {
      console.error("โหลดข้อความล้มเหลว:", err);
      setDefaultMessages([]);
      return [];
    }
  };

  const loadConversations = async (pageId) => {
    if (!pageId) return;

    setLoading(true);
    try {
      const conversations = await fetchConversations(pageId);
      console.log('📊 โหลดข้อมูลจาก database สำเร็จ');
      
      setConversations(conversations);
      setAllConversations(conversations);
      setLastUpdateTime(new Date());
      
      // Reset filters
      setFilters({
        disappearTime: "",
        startDate: "",
        endDate: "",
        customerType: "",
        platformType: "",
        miningStatus: ""
      });
      setFilteredConversations([]);
      setSelectedConversationIds([]);
    } catch (err) {
      console.error("❌ เกิดข้อผิดพลาด:", err);
      if (err.response?.status === 400) {
        alert("กรุณาเชื่อมต่อ Facebook Page ก่อนใช้งาน");
      } else {
        alert(`เกิดข้อผิดพลาด: ${err.message || err}`);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleloadConversations = () => {
    if (!selectedPage) {
      alert("กรุณาเลือกเพจ");
      return;
    }
    messageCache.current = {};
    loadConversations(selectedPage);
  };

  // Filter Functions
  const applyFilters = () => {
    let filtered = [...allConversations];
    const { disappearTime, customerType, platformType, miningStatus, startDate, endDate } = filters;

    if (disappearTime) {
      const now = new Date();
      filtered = filtered.filter(conv => {
        const referenceTime = conv.last_user_message_time || conv.updated_time;
        if (!referenceTime) return false;

        const updated = new Date(referenceTime);
        const diffDays = (now - updated) / (1000 * 60 * 60 * 24);

        switch (disappearTime) {
          case '1d': return diffDays <= 1;
          case '3d': return diffDays <= 3;
          case '7d': return diffDays <= 7;
          case '1m': return diffDays <= 30;
          case '3m': return diffDays <= 90;
          case '6m': return diffDays <= 180;
          case '1y': return diffDays <= 365;
          case 'over1y': return diffDays > 365;
          default: return true;
        }
      });
    }

    if (customerType) {
      filtered = filtered.filter(conv => conv.customerType === customerType);
    }

    if (platformType) {
      filtered = filtered.filter(conv => conv.platform === platformType);
    }

    if (miningStatus) {
      filtered = filtered.filter(conv => conv.miningStatus === miningStatus);
    }

    if (startDate) {
      const start = new Date(startDate);
      filtered = filtered.filter(conv => new Date(conv.created_time) >= start);
    }
    
    if (endDate) {
      const end = new Date(endDate);
      filtered = filtered.filter(conv => new Date(conv.created_time) <= end);
    }

    setFilteredConversations(filtered);
  };

  const handleClearDateFilter = () => {
    setSyncDateRange(null);
    loadConversations(selectedPage);
  };

  // Message Sending Functions
  const sendMessagesBySelectedSets = async (messageSetIds) => {
    if (!Array.isArray(messageSetIds) || selectedConversationIds.length === 0) {
      return;
    }

    // Check daily limit
    const selectedCount = selectedConversationIds.length;
    const remaining = getRemainingMines();
    
    if (remaining === 0) {
      showNotification('error', 'ถึงขีดจำกัดประจำวันแล้ว', `คุณได้ขุดครบ ${dailyMiningLimit} ครั้งแล้ววันนี้`);
      return;
    }
    
    if (selectedCount > remaining) {
      showNotification('warning', 'เกินขีดจำกัด', `คุณสามารถขุดได้อีก ${remaining} ครั้งเท่านั้นในวันนี้`);
      return;
    }

    try {
      let successCount = 0;
      let failCount = 0;

      showNotification('send', 'กำลังส่งข้อความ...', `ส่งไปยัง ${selectedConversationIds.length} การสนทนา`);

      for (const conversationId of selectedConversationIds) {
        const selectedConv = displayData.find(conv => conv.conversation_id === conversationId);
        const psid = selectedConv?.raw_psid;

        if (!psid) {
          failCount++;
          continue;
        }

        try {
          for (const setId of messageSetIds) {
            const response = await fetch(`http://localhost:8000/custom_messages/${setId}`);
            if (!response.ok) continue;
            
            const messages = await response.json();
            const sortedMessages = messages.sort((a, b) => a.display_order - b.display_order);

            for (const messageObj of sortedMessages) {
              let messageContent = messageObj.content;

              if (messageObj.message_type === "image") {
                messageContent = `http://localhost:8000/images/${messageContent.replace('[IMAGE] ', '')}`;
              } else if (messageObj.message_type === "video") {
                messageContent = `http://localhost:8000/videos/${messageContent.replace('[VIDEO] ', '')}`;
              }

              await fetch(`http://localhost:8000/send/${selectedPage}/${psid}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                  message: messageContent,
                  type: messageObj.message_type,
                  is_system_message: true
                }),
              });

              await new Promise(resolve => setTimeout(resolve, 500));
            }

            await new Promise(resolve => setTimeout(resolve, 1000));
          }
          
          successCount++;
        } catch (err) {
          console.error(`ส่งข้อความไม่สำเร็จสำหรับ ${conversationId}:`, err);
          failCount++;
        }
      }

      removeNotification();

      if (successCount > 0) {   
        // Update mining count
        updateMiningCount(successCount);
        
        showNotification('success', `ส่งข้อความสำเร็จ ${successCount} การสนทนา`, 
          `ขุดไปแล้ว ${todayMiningCount + successCount}/${dailyMiningLimit} ครั้งวันนี้`);
        setSelectedConversationIds([]);
      } else {
        showNotification('error', `ส่งข้อความไม่สำเร็จ ${failCount} การสนทนา`);
      }
      
    } catch (error) {
      console.error("เกิดข้อผิดพลาดในการส่งข้อความ:", error);
      alert("เกิดข้อผิดพลาดในการส่งข้อความ");
    }
  };

  // Notification Functions
  const showNotification = (type, message, detail = '') => {
    const notification = document.createElement('div');
    notification.className = `${type}-notification`;
    
    const icons = {
      success: '✅',
      error: '❌',
      warning: '⚠️',
      send: '🚀'
    };
    
    notification.innerHTML = `
      <div class="notification-content">
        <span class="notification-icon">${icons[type]}</span>
        <div class="notification-text">
          <strong>${message}</strong>
          ${detail ? `<span>${detail}</span>` : ''}
        </div>
      </div>
    `;
    
    document.body.appendChild(notification);
    
    if (type !== 'send') {
      setTimeout(() => notification.remove(), 3000);
    }
  };

  const removeNotification = () => {
    const notifications = document.querySelectorAll('.send-notification');
    notifications.forEach(n => n.remove());
  };

  // Popup Handlers
  const handleOpenPopup = () => {
    // Allow opening popup even if limit reached
    setIsPopupOpen(true);
  };

  const handleClosePopup = () => {
    setIsPopupOpen(false);
  };

  const handleConfirmPopup = (checkedSetIds) => {
    setSelectedMessageSetIds(checkedSetIds);
    setIsPopupOpen(false);
    sendMessagesBySelectedSets(checkedSetIds);
  };

  // Inactivity Data Functions
  const sendInactivityBatch = useCallback(async () => {
    if (!selectedPage || displayData.length === 0) return;
    
    try {
      const userData = displayData.map(conv => {
        const inactivityInfo = userInactivityData[conv.raw_psid] || {};
        return {
          user_id: conv.raw_psid,
          conversation_id: conv.conversation_id,
          last_message_time: conv.last_user_message_time || conv.updated_time,
          inactivity_minutes: inactivityInfo.minutes || calculateInactivityMinutes(
            conv.last_user_message_time,
            conv.updated_time
          )
        };
      });
      
      const response = await fetch(`http://localhost:8000/update-user-inactivity/${selectedPage}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ users: userData })
      });
      
      if (!response.ok) {
        throw new Error('Failed to update inactivity data');
      }
      
      const result = await response.json();
      console.log('✅ Batch update inactivity data:', result);

    } catch (error) {
      console.error('❌ Error sending inactivity batch:', error);
    }
  }, [selectedPage, displayData, userInactivityData]);

  const calculateInactivityMinutes = (lastMessageTime, updatedTime) => {
    const referenceTime = lastMessageTime || updatedTime;
    if (!referenceTime) return 0;
    
    const past = new Date(referenceTime);
    const now = new Date();
    const diffMs = now.getTime() - past.getTime();
    const diffMinutes = Math.floor(diffMs / 60000);
    
    return diffMinutes > 0 ? diffMinutes : 0;
  };

  // Effects
  useEffect(() => {
    // Reset daily count at midnight
    const checkMidnight = setInterval(() => {
      resetDailyCount();
    }, 60000); // Check every minute

    return () => clearInterval(checkMidnight);
  }, []);

  useEffect(() => {
    const handlePageChange = (event) => {
      const newPageId = event.detail.pageId;
      setSelectedPage(newPageId);
    };

    window.addEventListener('pageChanged', handlePageChange);
    
    const savedPage = localStorage.getItem("selectedPage");
    if (savedPage) {
      setSelectedPage(savedPage);
    }

    fetchPages()
      .then(setPages)
      .catch(err => console.error("ไม่สามารถโหลดเพจได้:", err));

    if (Notification.permission === "default") {
      Notification.requestPermission();
    }

    // Reset daily count on load
    resetDailyCount();

    return () => {
      window.removeEventListener('pageChanged', handlePageChange);
    };
  }, []);

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const pageIdFromURL = urlParams.get("page_id");
    if (pageIdFromURL) {
      setPageId(pageIdFromURL);
    }
  }, []);

  useEffect(() => {
    if (selectedPage) {
      Promise.all([
        loadMessages(selectedPage),
        loadConversations(selectedPage)
      ]).catch(err => console.error("Error loading data:", err));
    } else {
      setDefaultMessages([]);
      setConversations([]);
    }
  }, [selectedPage]);

  useEffect(() => {
    clockIntervalRef.current = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => {
      if (clockIntervalRef.current) clearInterval(clockIntervalRef.current);
    };
  }, []);

  useEffect(() => {
    if (selectedPage) {
      const interval = setInterval(() => {
        loadConversations(selectedPage);
      }, 15000);

      return () => clearInterval(interval);
    }
  }, [selectedPage]);

  useEffect(() => {
    if (inactivityUpdateTimerRef.current) {
      clearInterval(inactivityUpdateTimerRef.current);
    }
    
    sendInactivityBatch();
    
    inactivityUpdateTimerRef.current = setInterval(() => {
      sendInactivityBatch();
    }, 30000);
    
    return () => {
      if (inactivityUpdateTimerRef.current) {
        clearInterval(inactivityUpdateTimerRef.current);
      }
    };
  }, [sendInactivityBatch]);

  // Render
  return (
    <div className="app-container">
      <Sidebar />

      <main className="main-dashboard">
        <HeroSection />
        
        <CustomerStatistics selectedPage={selectedPage} />
        
        <ConnectionStatusBar
          selectedPage={selectedPage}
          selectedPageInfo={selectedPageInfo}
          lastUpdateTime={lastUpdateTime}
          currentTime={currentTime}
          onSyncComplete={(dateRange) => {
            setSyncDateRange(dateRange);
            loadConversations(selectedPage);
          }}
          syncDateRange={syncDateRange}
          onClearDateFilter={handleClearDateFilter}
        />
        
        <FileUploadSection 
          displayData={displayData}
          onSelectUsers={(conversationIds) => {
            setSelectedConversationIds(prev => {
              const newIds = [...new Set([...prev, ...conversationIds])];
              return newIds;
            });
          }}
          onClearSelection={() => setSelectedConversationIds([])} 
        />
        
        <FilterSection
          showFilter={showFilter}
          onToggleFilter={() => setShowFilter(prev => !prev)}
          filters={filters}
          onFilterChange={(newFilters) => setFilters(newFilters)}
          onApplyFilters={applyFilters}
          onClearFilters={() => {
            setFilteredConversations([]);
            setFilters({
              disappearTime: "",
              startDate: "",
              endDate: "",
              customerType: "",
              platformType: "",
              miningStatus: ""
            });
          }}
        />
        
        <AlertMessages
          selectedPage={selectedPage}
          conversationsLength={conversations.length}
          loading={loading}
          filteredLength={filteredConversations.length}
          allLength={allConversations.length}
        />

        <div className="content-area">
          {loading ? (
            <LoadingState />
          ) : displayData.length === 0 ? (
            <EmptyState selectedPage={selectedPage} />
          ) : (
            <ConversationTable
              displayData={displayData}
              selectedConversationIds={selectedConversationIds}
              onToggleCheckbox={toggleCheckbox}
              onToggleAll={(checked) => {
                if (checked) {
                  setSelectedConversationIds(displayData.map(conv => conv.conversation_id));
                } else {
                  setSelectedConversationIds([]);
                }
              }}
              onInactivityChange={handleInactivityChange}
            />
          )}
        </div>

        <ActionBar
          selectedCount={selectedConversationIds.length}
          totalCount={displayData.length}
          loading={loading}
          selectedPage={selectedPage}
          onOpenPopup={handleOpenPopup}
          onRefresh={handleloadConversations}
          canMineMore={canMineMore()}
          remainingMines={getRemainingMines()}
        />

        {isPopupOpen && (
          <Popup
            selectedPage={selectedPage}
            onClose={handleClosePopup}
            defaultMessages={defaultMessages}
            onConfirm={handleConfirmPopup}
            count={selectedConversationIds.length}
            remainingMines={getRemainingMines()}
            currentMiningCount={todayMiningCount}
            dailyMiningLimit={dailyMiningLimit}
            onLimitChange={(newLimit) => {
              setDailyMiningLimit(newLimit);
              localStorage.setItem('dailyMiningLimit', newLimit.toString());
            }}
          />
        )}
      </main>
    </div>
  );
}

export default App;