import * as crypto from 'crypto';
import { base58btc } from 'multiformats/bases/base58';

function generateKey() {
    console.log("Generating Ed25519 key pair...");
    const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');

    // Export private key in DER format
    const privBuffer = privateKey.export({ format: 'der', type: 'pkcs8' });
    // Raw Ed25519 private key is the last 32 bytes of the DER
    const rawPriv = privBuffer.slice(-32);
    const multibasePriv = 'z' + base58btc.encode(rawPriv);

    // Export public key in DER format
    const pubBufferArr = publicKey.export({ format: 'der', type: 'spki' });
    // Raw Ed25519 public key is the last 32 bytes of the DER
    const rawPub = pubBufferArr.slice(-32);

    // did:key:z + base58btc(multicodec(ed25519) + pubkey)
    const multicodecPub = Buffer.concat([Buffer.from([0xed, 0x01]), rawPub]);
    const didKey = 'did:key:z' + base58btc.encode(multicodecPub);

    console.log("\n=== NEW LABELER KEYS ===");
    console.log("PRIVATE KEY (Set as SIGNING_KEY in Render):");
    console.log(multibasePriv);
    console.log("\nPUBLIC KEY (did:key format):");
    console.log(didKey);
    console.log("=========================\n");
}

generateKey();
