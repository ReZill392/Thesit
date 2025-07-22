// =====================================================
// COMPONENT: EmptyState
// PURPOSE: แสดงเมื่อไม่มีข้อมูล
// FEATURES:
// - แสดง icon และข้อความเมื่อไม่มีข้อมูล
// - แตกต่างกันตามสถานะการเลือกเพจ
// =====================================================
export const EmptyState = ({ selectedPage }) => (
  <div className="empty-state">
    <div className="empty-icon">📭</div>
    <h3 className="empty-title">
      {selectedPage ? "ไม่พบข้อมูลการสนทนา" : "กรุณาเลือกเพจเพื่อแสดงข้อมูล"}
    </h3>
  </div>
);

export default EmptyState; // ✅
