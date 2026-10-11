#version 120
varying vec2 vUV;
    uniform float uDark;
    uniform sampler2D uScene;
    uniform vec2 uResolution;
    uniform vec4 uRect;
    uniform float uRadius;
    uniform float uMaterial;
    uniform vec3 uPointer;
    uniform vec4 uRipples[4];
    float roundedBox(vec2 p) {
      vec2 q = abs(p) - (uRect.zw*0.5 - uRadius);
      return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - uRadius;
    }
    vec2 sceneUV(vec2 p) {
      return clamp(vec2(p.x/uResolution.x, 1.0-p.y/uResolution.y), 0.002, 0.998);
    }
    void main() {
      vec2 screen = vec2(vUV.x, 1.0-vUV.y)*uResolution;
      vec2 local = screen - uRect.xy - uRect.zw*0.5;
      float d = roundedBox(local);
      if (d > 1.5) discard;
      vec2 normal = normalize(vec2(roundedBox(local+vec2(0.7,0.0))-roundedBox(local-vec2(0.7,0.0)),
                                  roundedBox(local+vec2(0.0,0.7))-roundedBox(local-vec2(0.0,0.7))) + vec2(0.0001));
      float rim = exp(min(d, 0.0)/11.0);
      vec2 bend = normal * rim * (17.0 + min(uRadius, 28.0)*0.4);
      vec2 delta = screen - uPointer.xy;
      float distanceToPointer = length(delta);
      float hover = exp(-distanceToPointer*distanceToPointer/22000.0)*uPointer.z;
      bend += delta * hover * 0.18;
      for (int i=0; i<4; i++) {
        vec2 wave = screen - uRipples[i].xy;
        float distanceToWave = length(wave);
        float age = uRipples[i].z;
        float ring = distanceToWave - age*220.0;
        float amplitude = exp(-age*2.0)*exp(-ring*ring/1200.0)*uRipples[i].w;
        bend += wave/max(distanceToWave,1.0)*sin(ring*0.085)*amplitude*13.0;
      }
      vec2 samplePoint = screen - bend;
      vec2 dispersion = normal*rim*1.35;
      vec3 color = vec3(texture2D(uScene,sceneUV(samplePoint+dispersion)).r,
                        texture2D(uScene,sceneUV(samplePoint)).g,
                        texture2D(uScene,sceneUV(samplePoint-dispersion)).b);
      // Frosted center keeps contrast; the edge retains the strongest refraction.
      vec3 soft = texture2D(uScene,sceneUV(samplePoint+vec2(3.0,2.0))).rgb;
      soft += texture2D(uScene,sceneUV(samplePoint-vec2(3.0,2.0))).rgb;
      color = mix(color, soft*0.5, (1.0-rim)*0.32);
      if (uMaterial > 0.5) {
        vec3 tint = uMaterial > 1.5 ? vec3(0.02,0.38,0.59) : vec3(0.045,0.29,0.43);
        color = mix(color, mix(tint, tint * 0.48, uDark), 0.77);
      } else {
        color = mix(color, mix(vec3(0.98,0.995,1.0), vec3(0.045,0.10,0.17), uDark), 0.35 + (1.0-rim)*0.13);
      }
      vec2 lightDirection = normalize(uPointer.xy - (uRect.xy+uRect.zw*0.5) + vec2(-180.0,-230.0));
      float reflection = pow(max(dot(normal,lightDirection),0.0),5.0);
      color += vec3(0.18,0.21,0.23)*rim*reflection;
      color += vec3(0.11,0.14,0.16)*hover;
      float edge = exp(-abs(d+1.5)*1.0);
      color += vec3(0.35)*edge*(0.25+reflection*0.75);
      color = mix(color, color * 0.84, uDark);
      gl_FragColor = vec4(color, 1.0-smoothstep(-0.75,1.0,d));
    }
