import React, { useState, useEffect } from 'react'

function ProfileRow({ profile, onEdit, onDelete }) {
  return (
    <tr className="border-t border-gray-700 hover:bg-gray-800/50">
      <td className="px-3 py-2 font-mono text-xs">{profile.profile_id.slice(0, 8)}...</td>
      <td className="px-3 py-2">{profile.name}</td>
      <td className="px-3 py-2 font-mono text-xs">{profile.fingerprint_seed}</td>
      <td className="px-3 py-2 text-xs text-gray-400">{profile.proxy || '-'}</td>
      <td className="px-3 py-2 text-xs">{profile.timezone || '-'}</td>
      <td className="px-3 py-2">
        <span className={`text-xs px-1.5 py-0.5 rounded ${profile.has_data ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'}`}>
          {profile.has_data ? 'has data' : 'empty'}
        </span>
      </td>
      <td className="px-3 py-2 space-x-2">
        <button onClick={() => onEdit(profile)} className="text-blue-400 hover:text-blue-300 text-sm">Edit</button>
        <button onClick={() => onDelete(profile.profile_id)} className="text-red-400 hover:text-red-300 text-sm">Delete</button>
      </td>
    </tr>
  )
}

function ProfileForm({ profile, onSave, onCancel }) {
  const [form, setForm] = useState({
    name: profile?.name || '',
    fingerprint_seed: profile?.fingerprint_seed || '',
    proxy: profile?.proxy || '',
    timezone: profile?.timezone || '',
    locale: profile?.locale || '',
    platform: profile?.platform || 'windows',
    user_agent: profile?.user_agent || '',
    screen_width: profile?.screen_width || 1920,
    screen_height: profile?.screen_height || 1080,
    notes: profile?.notes || '',
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    const data = { ...form }
    if (data.fingerprint_seed === '') delete data.fingerprint_seed
    else data.fingerprint_seed = parseInt(data.fingerprint_seed)
    if (!data.proxy) data.proxy = null
    if (!data.timezone) data.timezone = null
    if (!data.locale) data.locale = null
    if (!data.user_agent) data.user_agent = null
    if (!data.notes) data.notes = null
    onSave(data)
  }

  const field = (label, key, type = 'text') => (
    <div>
      <label className="block text-xs text-gray-400 mb-1">{label}</label>
      <input type={type} value={form[key]} onChange={e => setForm({...form, [key]: e.target.value})}
        className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm" />
    </div>
  )

  return (
    <form onSubmit={handleSubmit} className="bg-gray-800 border border-gray-700 rounded-lg p-4 mb-4">
      <div className="grid grid-cols-3 gap-3 mb-3">
        {field('Name', 'name')}
        {field('Fingerprint Seed', 'fingerprint_seed', 'number')}
        {field('Proxy', 'proxy')}
        {field('Timezone', 'timezone')}
        {field('Locale', 'locale')}
        <div>
          <label className="block text-xs text-gray-400 mb-1">Platform</label>
          <select value={form.platform} onChange={e => setForm({...form, platform: e.target.value})}
            className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm">
            <option value="windows">Windows</option>
            <option value="macos">macOS</option>
            <option value="linux">Linux</option>
          </select>
        </div>
        {field('User Agent', 'user_agent')}
        {field('Screen Width', 'screen_width', 'number')}
        {field('Screen Height', 'screen_height', 'number')}
      </div>
      <div className="mb-3">
        <label className="block text-xs text-gray-400 mb-1">Notes</label>
        <textarea value={form.notes} onChange={e => setForm({...form, notes: e.target.value})}
          className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm h-16" />
      </div>
      <div className="flex gap-2">
        <button type="submit" className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm">
          {profile ? 'Update' : 'Create'}
        </button>
        <button type="button" onClick={onCancel} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm">Cancel</button>
      </div>
    </form>
  )
}

export default function ProfileManager() {
  const [profiles, setProfiles] = useState([])
  const [editing, setEditing] = useState(null) // null=closed, 'new'=create, profile=edit
  const [loading, setLoading] = useState(true)

  const fetchProfiles = async () => {
    try {
      const r = await fetch('/api/profiles')
      if (r.ok) setProfiles(await r.json())
    } catch (e) {}
    setLoading(false)
  }

  useEffect(() => { fetchProfiles() }, [])

  const handleCreate = async (data) => {
    await fetch('/api/profiles', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) })
    setEditing(null)
    fetchProfiles()
  }

  const handleUpdate = async (data) => {
    await fetch(`/api/profiles/${editing.profile_id}`, { method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) })
    setEditing(null)
    fetchProfiles()
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this profile and all its data?')) return
    await fetch(`/api/profiles/${id}`, { method: 'DELETE' })
    fetchProfiles()
  }

  return (
    <div className="bg-gray-800/50 rounded-lg border border-gray-700 mb-6 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between">
        <span className="font-medium">Profiles（共享）</span>
        <button onClick={() => setEditing('new')} className="px-2 py-1 bg-blue-600 hover:bg-blue-500 rounded text-xs">+ New Profile</button>
      </div>
      <div className="p-4">
        {editing === 'new' && <ProfileForm onSave={handleCreate} onCancel={() => setEditing(null)} />}
        {editing && editing !== 'new' && <ProfileForm profile={editing} onSave={handleUpdate} onCancel={() => setEditing(null)} />}
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 text-left">
              <th className="px-3 py-2">ID</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Seed</th>
              <th className="px-3 py-2">Proxy</th>
              <th className="px-3 py-2">Timezone</th>
              <th className="px-3 py-2">Data</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {profiles.map(p => <ProfileRow key={p.profile_id} profile={p} onEdit={setEditing} onDelete={handleDelete} />)}
            {!loading && profiles.length === 0 && (
              <tr><td colSpan="7" className="px-3 py-6 text-center text-gray-500">No profiles</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
