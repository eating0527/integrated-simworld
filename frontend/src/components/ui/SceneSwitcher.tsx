import { SCENES, type SceneId } from '@/config/scenes.config';

interface SceneSwitcherProps {
  currentScene: SceneId;
  onChange: (id: SceneId) => void;
  hasPickedScene?: boolean;
  pickedActive?: boolean;
  pickedLabel?: string | null;
  onSelectPicked?: () => void;
}

export function SceneSwitcher({
  currentScene,
  onChange,
  hasPickedScene = false,
  pickedActive = false,
  pickedLabel,
  onSelectPicked,
}: SceneSwitcherProps) {
  const pickedSubtitle = (pickedLabel ?? '').trim() || '你選的地圖';

  return (
    <div style={{
      position: 'fixed',
      top: '16px',
      left: '50%',
      transform: 'translateX(-50%)',
      display: 'flex',
      gap: '8px',
      zIndex: 1000,
      background: 'rgba(10, 15, 30, 0.75)',
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      border: '1px solid rgba(255,255,255,0.12)',
      borderRadius: '12px',
      padding: '6px',
      boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
    }}>
      {SCENES.map(scene => {
        const active = currentScene === scene.id;
        return (
          <button
            key={scene.id}
            onClick={() => onChange(scene.id)}
            title={scene.label}
            style={{
              padding: '6px 18px',
              borderRadius: '8px',
              border: 'none',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: active ? 700 : 400,
              letterSpacing: '0.04em',
              transition: 'all 0.2s',
              background: active
                ? 'linear-gradient(135deg, rgba(99,179,237,0.9), rgba(129,140,248,0.9))'
                : 'transparent',
              color: active ? '#fff' : 'rgba(255,255,255,0.6)',
              boxShadow: active ? '0 2px 12px rgba(99,179,237,0.35)' : 'none',
            }}
          >
            {scene.labelEn}
            <span style={{
              display: 'block',
              fontSize: '10px',
              fontWeight: 400,
              opacity: 0.75,
              marginTop: '1px',
            }}>
              {scene.label}
            </span>
          </button>
        );
      })}

      <button
        key="picked-map"
        onClick={() => onSelectPicked?.()}
        title={hasPickedScene ? `${pickedSubtitle}（動態生成）` : '尚未有可用的動態地圖'}
        disabled={!hasPickedScene}
        style={{
          padding: '6px 18px',
          borderRadius: '8px',
          border: 'none',
          cursor: hasPickedScene ? 'pointer' : 'not-allowed',
          fontSize: '13px',
          fontWeight: pickedActive ? 700 : 400,
          letterSpacing: '0.04em',
          transition: 'all 0.2s',
          background: pickedActive
            ? 'linear-gradient(135deg, rgba(16,185,129,0.9), rgba(59,130,246,0.9))'
            : 'transparent',
          color: hasPickedScene
            ? (pickedActive ? '#fff' : 'rgba(255,255,255,0.7)')
            : 'rgba(255,255,255,0.35)',
          boxShadow: pickedActive ? '0 2px 12px rgba(16,185,129,0.35)' : 'none',
        }}
      >
        PICKED
        <span style={{
          display: 'block',
          fontSize: '10px',
          fontWeight: 400,
          opacity: 0.75,
          marginTop: '1px',
          maxWidth: '120px',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          {pickedSubtitle}
        </span>
      </button>
    </div>
  );
}
