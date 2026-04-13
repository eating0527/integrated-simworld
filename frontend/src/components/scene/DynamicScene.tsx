import { useMemo } from 'react';
import { useGLTF } from '@react-three/drei';
import * as THREE from 'three';

interface DynamicSceneProps {
  modelPath: string; // e.g., "/static/scenes/generated/{taskId}/scene.glb"
  position?: [number, number, number];
  scale?: number;
}

/**
 * DynamicScene — Loads and renders a dynamically generated GLB model
 * Used for user-selected map locations with blosm-generated OSM data
 */
export function DynamicScene({ modelPath, position = [0, 0, 0], scale = 1 }: DynamicSceneProps) {
  const { scene } = useGLTF(modelPath);

  const processedScene = useMemo(() => {
    const cloned = scene.clone(true);
    cloned.traverse((obj: THREE.Object3D) => {
      if ((obj as THREE.Mesh).isMesh) {
        const mesh = obj as THREE.Mesh;
        mesh.castShadow = true;
        mesh.receiveShadow = true;

        // Upgrade MeshBasicMaterial to MeshStandardMaterial for lighting support
        const upgrade = (mat: THREE.Material) => {
          if (mat instanceof THREE.MeshBasicMaterial) {
            const newMat = new THREE.MeshStandardMaterial({
              color: mat.color,
              map: mat.map,
            });
            mat.dispose();
            return newMat;
          }
          return mat;
        };

        if (Array.isArray(mesh.material)) {
          mesh.material = mesh.material.map(upgrade) as THREE.Material[];
        } else {
          mesh.material = upgrade(mesh.material);
        }
      }
    });
    return cloned;
  }, [scene]);

  return (
    <group position={position}>
      <primitive object={processedScene} scale={scale} />
    </group>
  );
}

// Optional preload for performance
export function preloadDynamicScene(modelPath: string) {
  useGLTF.preload(modelPath);
}
