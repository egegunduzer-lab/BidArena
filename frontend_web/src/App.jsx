import React, { useState } from 'react';
import './App.css';

function App() {
  const [teklif, setTeklif] = useState(35000);

  const teklifArtir = () => {
    setTeklif(prev => prev + 500);
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      backgroundColor: '#1e1e2e',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      color: '#ffffff',
      padding: '20px'
    }}>
      {/* Üst Başlık */}
      <h1 style={{
        fontSize: '2.5rem',
        fontWeight: 'bold',
        marginBottom: '40px',
        textAlign: 'center',
        letterSpacing: '-0.5px'
      }}>
        BidArena - Canlı Teklif Ekranı
      </h1>

      {/* Ürün & Teklif Kartı */}
      <div style={{
        width: '100%',
        maxWidth: '650px',
        backgroundColor: '#e0e0e0',
        borderRadius: '16px',
        padding: '40px',
        boxShadow: '0 10px 25px rgba(0,0,0,0.3)',
        color: '#111111',
        display: 'flex',
        flexDirection: 'column',
        gap: '24px',
        position: 'relative',
        minHeight: '350px'
      }}>
        
        {/* Ürün Bilgisi */}
        <div style={{ fontSize: '1.8rem', fontWeight: '600' }}>
          Ürünün Adı: <span style={{ fontWeight: '700' }}>Playstation 5</span>
        </div>

        {/* Güncel Teklif */}
        <div style={{ 
          fontSize: '2rem', 
          fontWeight: '700',
          color: '#2e7d32',
          backgroundColor: '#d4edda',
          padding: '12px 20px',
          borderRadius: '8px',
          display: 'inline-block',
          alignSelf: 'flex-start'
        }}>
          Güncel Teklif: {teklif.toLocaleString('tr-TR')} ₺
        </div>

        {/* İnternetten Bağımsız Şık Oyun Konsolu İkonu */}
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          margin: '15px 0',
          padding: '20px',
          backgroundColor: '#d5d5d5',
          borderRadius: '12px'
        }}>
          <svg width="110" height="110" viewBox="0 0 24 24" fill="none" stroke="#1e1e2e" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="6" y1="12" x2="10" y2="12"></line>
            <line x1="8" y1="10" x2="8" y2="14"></line>
            <line x1="15" y1="13" x2="15.01" y2="13"></line>
            <line x1="18" y1="11" x2="18.01" y2="11"></line>
            <rect x="2" y="6" width="20" height="12" rx="4"></rect>
          </svg>
        </div>

        {/* "Teklif Ver" Butonu */}
        <button 
          onClick={teklifArtir}
          style={{
            alignSelf: 'flex-end',
            backgroundColor: '#ff0000',
            color: '#ffffff',
            border: 'none',
            padding: '16px 40px',
            fontSize: '1.5rem',
            fontWeight: 'bold',
            borderRadius: '8px',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
            boxShadow: '0 4px 6px rgba(255, 0, 0, 0.2)',
            marginTop: 'auto'
          }}
          onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#cc0000'}
          onMouseOut={(e) => e.currentTarget.style.backgroundColor = '#ff0000'}
        >
          Teklif Ver
        </button>
      </div>
    </div>
  );
}

export default App;