import json
import struct

def parse_glb(file_path):
    with open(file_path, 'rb') as f:
        magic = f.read(4)
        if magic != b'glTF':
            print("Not a GLB file")
            return
        version = struct.unpack('<I', f.read(4))[0]
        length = struct.unpack('<I', f.read(4))[0]
        
        chunk_length = struct.unpack('<I', f.read(4))[0]
        chunk_type = f.read(4)
        if chunk_type != b'JSON':
            print("First chunk is not JSON")
            return
            
        json_data = f.read(chunk_length)
        gltf = json.loads(json_data.decode('utf-8'))
        
        morph_targets = set()
        for mesh in gltf.get('meshes', []):
            if 'extras' in mesh and 'targetNames' in mesh['extras']:
                for name in mesh['extras']['targetNames']:
                    morph_targets.add(name)
        
        if morph_targets:
            print("Found Morph Targets:")
            print(list(morph_targets)[:20]) # Print first 20
        else:
            print("No morph targets found in mesh extras. Checking primitives...")
            for mesh in gltf.get('meshes', []):
                for prim in mesh.get('primitives', []):
                    if 'targets' in prim:
                        print("Found targets in primitives but no names.")
                        break

parse_glb('d:/AI/Project_Aria/assets/avatar_3d.glb')
