import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import UploadForm from '../components/UploadForm'
import { checkFile } from '../fileChecks'
import { errorResponse, fakeFetch, makeJob } from './fixtures'

function audioFile(name = 'meeting.mp3', bytes = 1000): File {
  return new File([new Uint8Array(bytes)], name, { type: 'audio/mpeg' })
}

afterEach(() => vi.unstubAllGlobals())

describe('checkFile', () => {
  it('accepts supported audio', () => {
    expect(checkFile(audioFile('Team Sync.M4A'))).toBeNull()
  })

  it('rejects unsupported formats and lists the accepted ones', () => {
    expect(checkFile(audioFile('notes.pdf'))).toMatch(/"\.pdf" files are not supported.*\.mp3/)
  })

  it('rejects empty files', () => {
    expect(checkFile(audioFile('empty.wav', 0))).toMatch(/empty/)
  })

  it('rejects files over the limit', () => {
    const big = audioFile('long.mp3', 1)
    Object.defineProperty(big, 'size', { value: 201 * 1024 * 1024 })
    expect(checkFile(big)).toMatch(/201\.0 MB, above the 200 MB limit/)
  })
})

describe('UploadForm', () => {
  it('blocks an unsupported file with a message', async () => {
    const onSubmit = vi.fn()
    render(<UploadForm onSubmit={onSubmit} uploading={false} />)

    await userEvent.upload(screen.getByLabelText('Meeting recording'), audioFile('slides.pptx'), { applyAccept: false })

    expect(screen.getByRole('alert')).toHaveTextContent('".pptx" files are not supported')
    expect(screen.getByRole('button', { name: 'Process recording' })).toBeDisabled()
  })

  it('submits a valid file with the glossary', async () => {
    const onSubmit = vi.fn()
    render(<UploadForm onSubmit={onSubmit} uploading={false} />)

    await userEvent.upload(screen.getByLabelText('Meeting recording'), audioFile())
    await userEvent.type(screen.getByLabelText(/Terms used in this meeting/), 'Zephyr, KubeFlow')
    await userEvent.click(screen.getByRole('button', { name: 'Process recording' }))

    expect(screen.getByText('meeting.mp3')).toBeInTheDocument()
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ name: 'meeting.mp3' }), 'Zephyr, KubeFlow')
  })
})

describe('App upload', () => {
  it('sends the file and shows progress', async () => {
    const fetchMock = fakeFetch(makeJob('queued', ['pending', 'pending', 'pending']))
    render(<App />)

    await userEvent.upload(screen.getByLabelText('Meeting recording'), audioFile())
    await userEvent.click(screen.getByRole('button', { name: 'Process recording' }))

    expect(await screen.findByText('Transcribing the audio')).toBeInTheDocument()
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/meetings')
    expect((init.body as FormData).get('file')).toBeInstanceOf(File)
  })

  it("shows the backend's error with stage and fix", async () => {
    fakeFetch(errorResponse(400, 'File check', 'File check failed: the file could not be read as audio.', 'Check that the recording plays.'))
    render(<App />)

    await userEvent.upload(screen.getByLabelText('Meeting recording'), audioFile())
    await userEvent.click(screen.getByRole('button', { name: 'Process recording' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Stage: File check')
    expect(alert).toHaveTextContent('could not be read as audio')
    expect(alert).toHaveTextContent('What to do: Check that the recording plays.')

    await userEvent.click(screen.getByRole('button', { name: 'Try another file' }))
    expect(screen.getByRole('button', { name: 'Process recording' })).toBeInTheDocument()
  })

  it('explains when the server is unreachable', async () => {
    fakeFetch(new TypeError('Failed to fetch'))
    render(<App />)

    await userEvent.upload(screen.getByLabelText('Meeting recording'), audioFile())
    await userEvent.click(screen.getByRole('button', { name: 'Process recording' }))

    expect(await screen.findByRole('alert')).toHaveTextContent("Can't reach the server.")
  })

  it('treats a dev-proxy error without our error body as unreachable', async () => {
    fakeFetch(new Response('', { status: 500 }))
    render(<App />)

    await userEvent.upload(screen.getByLabelText('Meeting recording'), audioFile())
    await userEvent.click(screen.getByRole('button', { name: 'Process recording' }))

    expect(await screen.findByRole('alert')).toHaveTextContent("Can't reach the server.")
  })
})
