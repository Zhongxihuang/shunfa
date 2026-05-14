'use client';

import { getAdaptiveTextStyle, normalizeTemplateText, splitLead, PostTemplateProps, TEMPLATE_WIDTH, TEMPLATE_HEIGHT } from './shared';

export default function TemplateBeige({ pageText, pageIndex, totalPages }: PostTemplateProps) {
  const isCover = pageIndex === 0;
  const cleanText = normalizeTemplateText(pageText);
  const { lead, rest } = splitLead(cleanText);
  const bodyText = isCover && rest ? rest : cleanText;
  const bodyStyle = getAdaptiveTextStyle(bodyText, isCover ? 20 : 23);

  return (
    <div
      style={{
        width: TEMPLATE_WIDTH,
        height: TEMPLATE_HEIGHT,
        background: 'linear-gradient(180deg, #FFFDF9 0%, #F7F2EA 100%)',
        display: 'flex',
        flexDirection: 'column',
        padding: 24,
        boxSizing: 'border-box',
        fontFamily: 'var(--font-display), "Iowan Old Style", "Songti SC", "STSong", serif',
        position: 'relative',
        overflow: 'hidden',
        color: '#222320',
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: 'radial-gradient(rgba(70,85,75,0.11) 0.8px, transparent 0.8px)',
          backgroundSize: '12px 12px',
          opacity: 0.42,
        }}
      />

      <div
        style={{
          position: 'absolute',
          right: -44,
          top: 56,
          width: 142,
          height: 142,
          borderRadius: '50%',
          border: '1px solid rgba(111,135,115,0.20)',
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: 22,
          top: 22,
          right: 22,
          bottom: 22,
          border: '1px solid rgba(133,128,118,0.26)',
          borderRadius: 18,
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: 30,
          top: 30,
          right: 30,
          bottom: 30,
          border: '1px solid rgba(142,165,146,0.24)',
          borderRadius: 12,
        }}
      />

      <div
        style={{
          position: 'relative',
          zIndex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '3px 4px 0',
          fontFamily: 'var(--font-body), "PingFang SC", sans-serif',
        }}
      >
        <div style={{ color: '#86887F', fontSize: 10, letterSpacing: 0 }}>
          SHUNFA EDITORIAL
        </div>
        <div
          style={{
            minWidth: 42,
            height: 22,
            borderRadius: 999,
            border: '1px solid rgba(111,135,115,0.30)',
            color: '#46554B',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 10,
          }}
        >
          {String(pageIndex + 1).padStart(2, '0')}
        </div>
      </div>

      <main
        style={{
          position: 'relative',
          zIndex: 1,
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: isCover ? 'center' : 'flex-start',
          padding: isCover ? '54px 18px 36px' : '62px 18px 28px',
        }}
      >
        {isCover && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              marginBottom: 24,
              color: '#6F8773',
              fontFamily: 'var(--font-body), "PingFang SC", sans-serif',
              fontSize: 11,
              letterSpacing: 0,
            }}
          >
            <span style={{ width: 34, height: 1, backgroundColor: '#8EA592' }} />
            今日判断
          </div>
        )}

        {isCover && (
          <h1
            style={{
              margin: '0 0 24px',
              color: '#222320',
              fontSize: lead.length > 22 ? 34 : 40,
              lineHeight: 1.15,
              fontWeight: 700,
              letterSpacing: 0,
            }}
          >
            {lead}
          </h1>
        )}

        <div
          style={{
            width: isCover ? 72 : 44,
            height: 1,
            background: '#6F8773',
            marginBottom: isCover ? 24 : 26,
          }}
        />

        <p
          style={{
            ...bodyStyle,
            color: '#3D4039',
            margin: 0,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            overflowWrap: 'break-word',
            fontWeight: 500,
            letterSpacing: 0,
          }}
        >
          {bodyText}
        </p>
      </main>

      <div
        style={{
          position: 'relative',
          zIndex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderTop: '1px solid rgba(133,128,118,0.22)',
          padding: '12px 5px 2px',
          fontFamily: 'var(--font-body), "PingFang SC", sans-serif',
        }}
      >
        <div>
          <div style={{ fontSize: 10, color: '#46554B', fontWeight: 600, letterSpacing: 0 }}>可信观点卡</div>
          <div style={{ marginTop: 4, fontSize: 9, color: '#86887F', letterSpacing: 0 }}>quiet insight / daily signal</div>
        </div>
        <div
          style={{
            color: '#86887F',
            fontSize: 10,
            letterSpacing: 0,
          }}
        >
          {pageIndex + 1}/{totalPages}
        </div>
      </div>
    </div>
  );
}
