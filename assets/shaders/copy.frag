#version 120
varying vec2 vUV;
    uniform sampler2D uScene;
    void main() { gl_FragColor = texture2D(uScene,vUV); }
