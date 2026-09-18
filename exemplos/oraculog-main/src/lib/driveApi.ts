export interface GoogleDriveFile {
  id: string;
  name: string;
  mimeType: string;
  size?: string;
  modifiedTime?: string;
  createdTime?: string;
  description?: string;
  webViewLink?: string;
  iconLink?: string;
  thumbnailLink?: string;
  owners?: Array<{ displayName: string; emailAddress: string }>;
}

export function extractFolderId(urlOrId: string): string {
  const trimmed = urlOrId.trim();
  if (trimmed.includes('drive.google.com')) {
    const match = trimmed.match(/\/folders\/([a-zA-Z0-9_-]+)/);
    if (match && match[1]) {
      return match[1];
    }
    const idParam = trimmed.match(/[?&]id=([a-zA-Z0-9_-]+)/);
    if (idParam && idParam[1]) {
      return idParam[1];
    }
  }
  return trimmed;
}

export async function fetchDriveFolderMetadata(
  folderId: string,
  accessToken: string
): Promise<GoogleDriveFile> {
  const fields = 'id,name,mimeType,description,modifiedTime,createdTime,webViewLink,owners';
  const res = await fetch(`https://www.googleapis.com/drive/v3/files/${folderId}?fields=${fields}&supportsAllDrives=true`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Erro ao acessar pasta do Drive (${res.status}): ${errorText}`);
  }

  return res.json();
}

export async function listDriveFolderChildren(
  folderId: string,
  accessToken: string
): Promise<GoogleDriveFile[]> {
  const query = `'${folderId}' in parents and trashed = false`;
  const fields = 'nextPageToken,files(id,name,mimeType,size,modifiedTime,createdTime,description,webViewLink,iconLink,thumbnailLink,owners)';
  const url = `https://www.googleapis.com/drive/v3/files?q=${encodeURIComponent(
    query
  )}&fields=${encodeURIComponent(fields)}&pageSize=100&supportsAllDrives=true&includeItemsFromAllDrives=true`;

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Erro ao listar itens da pasta (${res.status}): ${errorText}`);
  }

  const data = await res.json();
  return data.files || [];
}

export async function fetchFileTextContent(
  fileId: string,
  mimeType: string,
  accessToken: string
): Promise<string> {
  let url = `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media&supportsAllDrives=true`;

  // If it's a Google Doc, export as plain text
  if (mimeType === 'application/vnd.google-apps.document') {
    url = `https://www.googleapis.com/drive/v3/files/${fileId}/export?mimeType=text/plain&supportsAllDrives=true`;
  }

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  if (!res.ok) {
    throw new Error(`Não foi possível carregar o conteúdo do arquivo (${res.status})`);
  }

  return res.text();
}
