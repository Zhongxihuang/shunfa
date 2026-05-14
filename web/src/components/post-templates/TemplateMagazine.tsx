'use client';

import { getAdaptiveTextStyle, normalizeTemplateText, splitLead, PostTemplateProps, TEMPLATE_WIDTH, TEMPLATE_HEIGHT } from './shared';

const INDEX_LABELS = ['A', 'B', 'C', 'D'];

export default function TemplateMagazine({ pageText, pageIndex, totalPages }: PostTemplateProps) {
  const isCover = pageIndex === 0;
  const indexLabel = INDEX_LABELS[pageIndex % INDEX_LABELS.length];
  const cleanText = normalizeTemplateText(pageText);
  const { lead, rest } = splitLead(cleanText);
  const bodyText = isCover && rest ? rest : cleanText;
  const bodyStyle = getAdaptiveTextStyle(bodyText, isCover ? 19 : 22);

  return (
    <div
      style={{
        width: TEMPLATE_WIDTH,
        height: TEMPLATE_HEIGHT,
        background: '#EDE7DD',
        display: 'flex',
        flexDirection: 'column',
        padding: 22,
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
          backgroundImage: 'linear-gradient(90deg, rgba(70,85,75,0.07) 1px, transparent 1px)',
          backgroundSize: '28px 28px',
          opacity: 0.55,
        }}
      />

      <div
        style={{
          position: 'absolute',
          inset: 22,
          background: '#FFFDF8',
          borderRadius: 18,
          border: '1px solid rgba(133,128,118,0.25)',
          boxShadow: '0 22px 50px rgba(34,35,32,0.08)',
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: 22,
          top: 22,
          bottom: 22,
          width: 86,
          borderRadius: '18px 0 0 18px',
          background: 'linear-gradient(180deg, #46554B 0%, #2F3932 100%)',
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: 42,
          top: 48,
          width: 44,
          height: 44,
          borderRadius: '50%',
          border: '1px solid rgba(255,253,248,0.42)',
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: 62,
          bottom: 50,
          top: 122,
          width: 1,
          background: 'rgba(255,253,248,0.30)',
        }}
      />

      <div
        style={{
          position: 'relative',
          zIndex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          height: 40,
          marginLeft: 100,
          paddingRight: 10,
          fontFamily: 'var(--font-body), "PingFang SC", sans-serif',
        }}
      >
        <div style={{ color: '#86887F', fontSize: 10, letterSpacing: 0 }}>
          RESEARCH INDEX
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            color: '#6F8773',
            fontSize: 10,
            letterSpacing: 0,
          }}
        >
          <span>ISSUE</span>
          <span>{String(pageIndex + 1).padStart(2, '0')}</span>
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          zIndex: 1,
          left: 40,
          top: 106,
          width: 46,
          height: 46,
          borderRadius: '50%',
          background: '#FFFDF8',
          color: '#46554B',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 25,
          lineHeight: 1,
        }}
      >
        {indexLabel}
      </div>

      <main
        style={{
          position: 'relative',
          zIndex: 1,
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          marginLeft: 100,
          padding: isCover ? '38px 12px 28px 2px' : '44px 12px 28px 2px',
        }}
      >
        <div
          style={{
            borderTop: '1px solid rgba(133,128,118,0.26)',
            borderBottom: '1px solid rgba(133,128,118,0.22)',
            padding: isCover ? '26px 0 28px' : '28px 0',
          }}
        >
          {isCover && (
            <div
              style={{
                width: 'fit-content',
                maxWidth: '100%',
                padding: '6px 9px',
                borderRadius: 0,
                backgroundColor: '#F1ECE4',
                border: '1px solid rgba(142,165,146,0.24)',
                color: '#46554B',
                fontFamily: 'var(--font-body), "PingFang SC", sans-serif',
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: 0,
                marginBottom: 22,
              }}
            >
              VERIFIED NOTE
            </div>
          )}

          {isCover && (
            <h1
              style={{
                margin: '0 0 24px',
                color: '#222320',
                fontSize: lead.length > 22 ? 31 : 37,
                lineHeight: 1.16,
                fontWeight: 700,
                letterSpacing: 0,
              }}
            >
              {lead}
            </h1>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 22 }}>
            <span style={{ width: 38, height: 1, background: '#6F8773' }} />
            <span style={{ flex: 1, height: 1, backgroundColor: 'rgba(133,128,118,0.22)' }} />
          </div>

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
        </div>
      </main>

      <div
        style={{
          position: 'relative',
          zIndex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginLeft: 100,
          padding: '0 10px 0 0',
          fontFamily: 'var(--font-body), "PingFang SC", sans-serif',
        }}
      >
        <div>
          <div style={{ color: '#46554B', fontSize: 10, fontWeight: 600, letterSpacing: 0 }}>顺发内容索引</div>
          <div style={{ marginTop: 7, width: 126, height: 3, borderRadius: 999, backgroundColor: 'rgba(133,128,118,0.18)', overflow: 'hidden' }}>
            <div style={{ width: `${((pageIndex + 1) / totalPages) * 100}%`, height: '100%', borderRadius: 999, background: '#6F8773' }} />
          </div>
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
