async function request(path, options = {}) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    const detail = await resp
      .json()
      .then((body) => body.detail)
      .catch(() => null);
    throw new Error(detail || `${options.method || "GET"} ${path} failed: ${resp.status}`);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export const api = {
  listFolders: () => request("/api/folders"),
  createFolder: (name) =>
    request("/api/folders", { method: "POST", headers: jsonHeaders(), body: JSON.stringify({ name }) }),
  renameFolder: (id, name) =>
    request(`/api/folders/${id}`, { method: "PATCH", headers: jsonHeaders(), body: JSON.stringify({ name }) }),
  deleteFolder: (id) => request(`/api/folders/${id}`, { method: "DELETE" }),

  listPapers: (folderId) =>
    request(`/api/papers${folderId != null ? `?folder_id=${folderId}` : ""}`),
  uploadPaper: (file, folderId) => {
    const form = new FormData();
    form.append("file", file);
    const qs = folderId != null ? `?folder_id=${folderId}` : "";
    return request(`/api/papers${qs}`, { method: "POST", body: form });
  },
  importPaperFromUrl: (url, folderId) =>
    request("/api/papers/url", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ url, folder_id: folderId }),
    }),
  movePaper: (id, folderId) =>
    request(`/api/papers/${id}`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify({ folder_id: folderId }),
    }),
  renamePaper: (id, title) =>
    request(`/api/papers/${id}`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify({ title }),
    }),
  savePosition: (id, page, offset) =>
    request(`/api/papers/${id}`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify({ last_page: page, last_offset: offset }),
    }),
  setPaperRead: (id, read) =>
    request(`/api/papers/${id}`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify({ read }),
    }),
  deletePaper: (id) => request(`/api/papers/${id}`, { method: "DELETE" }),
  paperFileUrl: (id) => `/api/papers/${id}/file`,
  paperHtmlUrl: (id) => `/api/papers/${id}/html`,

  listHighlights: (paperId) => request(`/api/papers/${paperId}/highlights`),
  createHighlight: (paperId, payload) =>
    request(`/api/papers/${paperId}/highlights`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    }),
  updateHighlight: (paperId, highlightId, payload) =>
    request(`/api/papers/${paperId}/highlights/${highlightId}`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    }),
  deleteHighlight: (paperId, highlightId) =>
    request(`/api/papers/${paperId}/highlights/${highlightId}`, { method: "DELETE" }),

  addComment: (paperId, highlightId, body) =>
    request(`/api/papers/${paperId}/highlights/${highlightId}/comments`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ body }),
    }),
  editComment: (paperId, highlightId, commentId, body) =>
    request(`/api/papers/${paperId}/highlights/${highlightId}/comments/${commentId}`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify({ body }),
    }),
  deleteComment: (paperId, highlightId, commentId) =>
    request(`/api/papers/${paperId}/highlights/${highlightId}/comments/${commentId}`, {
      method: "DELETE",
    }),
};

function jsonHeaders() {
  return { "Content-Type": "application/json" };
}
