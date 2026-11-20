// The pictures of a plugin's README (PluginReadme.vue). The editor's img-src is 'self' (as for store.png), so a picture
// comes through the app, which fetches it from the plugin's own folder at its commit (GET api/plugins/<id>/readme/<path>,
// plugins.readme_image). A relative path is one of the plugin's folder; a full address counts only when it is a raw file
// of the plugin's own repository. Any other picture is left out ("").

// Raw files of the plugin's repository, from the link the add-on gives (Entry.link: the folder at its commit).
const rawBase = (repo: string) => {
  const match = repo.match(/^https:\/\/github\.com\/([^/]+)\/([^/]+)(?:\/tree\/([^/]+)\/(.*))?$/);
  return match ? `https://raw.githubusercontent.com/${match[1]}/${match[2]}/${match[3] || "HEAD"}/${match[4] ? `${match[4]}/` : ""}` : "";
};

export function readmePicture(src: string, repo: string, plugin: string, version?: string | null): string {
  const base = rawBase(repo);
  const own = /^[a-z][a-z0-9+.-]*:|^\/\//i.test(src) ? (base && src.startsWith(base) ? src.slice(base.length) : "") : src;
  const path = own.split(/[?#]/)[0].replace(/^(\.\/)+/, "");
  if (!plugin || !path || path.split("/").some((part) => !part || part.startsWith("."))) return "";
  const address = `api/plugins/${encodeURIComponent(plugin)}/readme/${path.split("/").map(encodeURIComponent).join("/")}`;
  return version ? `${address}?v=${encodeURIComponent(version)}` : address;
}
