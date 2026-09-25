// Self-contained browser entry: Editor and its React renderer share one dependency graph.
import React from "react";
import { createRoot } from "react-dom/client";
import SwaggerEditor from "./src/App.tsx";

export default function mountSwaggerEditor(element, props) {
  const root = createRoot(element);
  root.render(React.createElement(SwaggerEditor, props));
  return root;
}
