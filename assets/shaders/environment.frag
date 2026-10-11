#version 120
varying vec2 vUV;
    uniform float uDark;
    uniform vec2 uResolution;
    uniform vec2 uPointer;
    uniform float uTime;
    float cloud(vec2 p, vec2 center, vec2 stretch) {
      vec2 d = (p - center) / stretch;
      return exp(-dot(d, d) * 2.0);
    }
    void main() {
      vec2 p = vec2(vUV.x, 1.0 - vUV.y);
      float t = uTime * 0.045;
      vec3 color = vec3(0.85, 0.94, 0.97);
      color = mix(color, vec3(0.32, 0.78, 0.89), cloud(p, vec2(0.13 + sin(t)*0.04, 0.20), vec2(0.60, 0.65))*0.78);
      color = mix(color, vec3(0.76, 0.73, 0.93), cloud(p, vec2(0.90, 0.25 + cos(t)*0.05), vec2(0.46, 0.58))*0.65);
      color = mix(color, vec3(0.46, 0.87, 0.69), cloud(p, vec2(0.78, 0.88), vec2(0.65, 0.53))*0.70);
      // Broad, flowing ribbons give the lenses an actual texture to bend.
      float ribbon = p.y - (0.28 + 0.25*sin(p.x*4.1 + t) + 0.045*sin(p.x*10.0-t*0.8));
      color = mix(color, vec3(0.94, 0.99, 1.0), exp(-ribbon*ribbon*200.0)*0.68);
      float seam = abs(ribbon - 0.038);
      color += vec3(0.17, 0.20, 0.22) * exp(-seam*seam*14000.0);
      float second = p.y - (0.74 + 0.17*cos(p.x*5.2 - t*0.7));
      color = mix(color, vec3(0.46, 0.80, 0.88), exp(-second*second*550.0)*0.24);
      color += vec3(0.15) * exp(-pow(second - 0.019, 2.0)*14000.0);
      // Soft light tracks the pointer, without painting over interface text.
      vec2 light = (p*uResolution - uPointer) / 260.0;
      color += vec3(0.07, 0.08, 0.085)*exp(-dot(light, light));
      color = mix(color, color * vec3(0.14, 0.20, 0.29), uDark);
      gl_FragColor = vec4(color, 1.0);
    }
